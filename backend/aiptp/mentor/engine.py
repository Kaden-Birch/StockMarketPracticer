"""Persistent-mentor analysis engine (roadmap 8.1).

Every insight is DETERMINISTIC — computed from the transaction log, current
valuations, and the XP trail, with the backing numbers stored as evidence.
The LLM (when a model is loaded) only narrates these grounded findings; it
never invents observations. Runs upsert observations by (user, code): codes
that stop firing are marked RESOLVED, not deleted — the mentor remembers
what you fixed.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.service import diversification
from ..gamify.service import get_profile
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import (
    AutomationRule,
    BacktestRun,
    MentorObservation,
    MentorProfile,
    ObservationStatus,
    OrderSide,
    Portfolio,
    RecurringPlan,
    Transaction,
    TransactionKind,
    utcnow,
)

log = logging.getLogger(__name__)


@dataclass
class Insight:
    code: str
    category: str  # behavior | allocation | knowledge | strength
    severity: str  # info | notice | important
    title: str
    body: str
    evidence: dict = field(default_factory=dict)


@dataclass
class ClosedTrade:
    symbol: str
    hold_days: float
    pnl: Decimal


def _closed_trades(txns: list[Transaction]) -> list[ClosedTrade]:
    """FIFO walk over the trade log: each sell consumes the oldest open buys,
    yielding an (approximate, deterministic) holding period per closed lot."""
    open_lots: dict[str, list[tuple[Decimal, datetime]]] = {}
    closed: list[ClosedTrade] = []
    for t in txns:
        if t.kind != TransactionKind.TRADE:
            continue
        when = t.executed_at
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if t.side == OrderSide.BUY:
            open_lots.setdefault(t.symbol, []).append((t.quantity, when))
            continue
        remaining = t.quantity
        lots = open_lots.get(t.symbol, [])
        weighted_days = Decimal("0")
        consumed = Decimal("0")
        while remaining > 0 and lots:
            qty, acquired = lots[0]
            take = min(qty, remaining)
            days = Decimal(str((when - acquired).total_seconds() / 86400))
            weighted_days += take * days
            consumed += take
            remaining -= take
            if take == qty:
                lots.pop(0)
            else:
                lots[0] = (qty - take, acquired)
        if consumed > 0:
            closed.append(ClosedTrade(
                symbol=t.symbol,
                hold_days=float(weighted_days / consumed),
                pnl=t.realized_pnl if t.realized_pnl is not None else Decimal("0"),
            ))
    return closed


def analyze(session: Session, market: MarketDataService, username: str) -> dict:
    """Run every analyzer, persist observations + profile, return the view.
    The caller commits."""
    portfolios = session.scalars(
        select(Portfolio).where(
            Portfolio.owner == username,
            Portfolio.scenario_session_id.is_(None),
        )
    ).all()
    txns: list[Transaction] = []
    for p in portfolios:
        txns.extend(session.scalars(
            select(Transaction).where(Transaction.portfolio_id == p.id)
            .order_by(Transaction.executed_at)
        ))
    txns.sort(key=lambda t: t.executed_at)

    insights: list[Insight] = []
    traits: dict = {"portfolios": len(portfolios), "trades": 0}

    # ---- behavior: holding periods (disposition effect, panic sells) ----
    closed = _closed_trades(txns)
    trades = [t for t in txns if t.kind == TransactionKind.TRADE]
    traits["trades"] = len(trades)
    winners = [c for c in closed if c.pnl > 0]
    losers = [c for c in closed if c.pnl < 0]
    if winners:
        traits["avg_hold_winners_days"] = round(
            sum(c.hold_days for c in winners) / len(winners), 1)
    if losers:
        traits["avg_hold_losers_days"] = round(
            sum(c.hold_days for c in losers) / len(losers), 1)
    if closed:
        traits["avg_hold_days"] = round(
            sum(c.hold_days for c in closed) / len(closed), 1)

    if (len(winners) >= 3 and losers
            and traits["avg_hold_winners_days"] < 30
            and traits["avg_hold_winners_days"] < traits["avg_hold_losers_days"]):
        insights.append(Insight(
            code="sells_winners_early", category="behavior", severity="important",
            title="You often sell winners too early",
            body=(f"Your winning positions are held {traits['avg_hold_winners_days']} "
                  f"days on average, but losers {traits['avg_hold_losers_days']} days. "
                  "Cutting winners while riding losers (the disposition effect) is one "
                  "of the most common return killers."),
            evidence={"winners": len(winners), "losers": len(losers),
                      "avg_hold_winners": traits["avg_hold_winners_days"],
                      "avg_hold_losers": traits["avg_hold_losers_days"]},
        ))

    quick_loss_sells = [c for c in closed if c.pnl < 0 and c.hold_days <= 7]
    if len(quick_loss_sells) >= 2:
        insights.append(Insight(
            code="panic_selling", category="behavior", severity="notice",
            title="Several positions were sold at a loss within a week",
            body=(f"{len(quick_loss_sells)} positions were closed at a loss less than "
                  "7 days after buying. Rapid round-trips usually mean the entry had "
                  "no plan — decide an exit rule before you buy."),
            evidence={"quick_loss_sells": len(quick_loss_sells)},
        ))

    if closed and len(closed) >= 3 and traits.get("avg_hold_days", 0) > 60:
        insights.append(Insight(
            code="patient_holder", category="strength", severity="info",
            title="Strength: you let positions develop",
            body=(f"Closed positions were held {traits['avg_hold_days']} days on "
                  "average — patience is a real edge in long-horizon investing."),
            evidence={"avg_hold_days": traits["avg_hold_days"]},
        ))

    # ---- behavior: trading frequency (educational, never rewarded) ----
    now = utcnow()
    recent = [t for t in trades
              if (now - (t.executed_at.replace(tzinfo=timezone.utc)
                         if t.executed_at.tzinfo is None else t.executed_at)).days <= 30]
    traits["trades_last_30d"] = len(recent)
    if len(recent) > 20:
        insights.append(Insight(
            code="frequent_trading", category="behavior", severity="notice",
            title="High trading frequency this month",
            body=(f"{len(recent)} trades in 30 days. Frequent trading rarely beats "
                  "patience once spreads and taxes exist in the real world — make "
                  "sure each trade has a thesis."),
            evidence={"trades_last_30d": len(recent)},
        ))

    # ---- allocation: valuation-based checks over live portfolios ----
    best_div: float | None = None
    total_value = Decimal("0")
    total_cash = Decimal("0")
    domestic_only = True
    any_positions = False
    for p in portfolios:
        try:
            view = value_portfolio(p, market)
        except MarketDataError:
            continue
        total_value += Decimal(view["total_value"])
        total_cash += Decimal(view["cash_balance"])
        if view["holdings"]:
            any_positions = True
        d = diversification(view).get("score")
        if d is not None and (best_div is None or d > best_div):
            best_div = d
    for t in trades:
        if t.quote_currency not in ("", "USD") or t.fx_rate != Decimal("1"):
            domestic_only = False
            break
    traits["best_diversification"] = best_div
    if total_value > 0:
        traits["cash_pct"] = round(float(total_cash / total_value * 100), 1)

    if any_positions and domestic_only and len(trades) >= 5:
        insights.append(Insight(
            code="no_international_exposure", category="allocation", severity="notice",
            title="Your portfolio lacks international exposure",
            body=("Every trade so far settled in USD at 1.0 FX — everything you own "
                  "is domestic. Adding non-US names (or an international index) "
                  "reduces single-economy risk."),
            evidence={"trades_checked": len(trades)},
        ))

    if best_div is not None and best_div < 40 and any_positions:
        insights.append(Insight(
            code="concentrated_portfolio", category="allocation", severity="important",
            title="Heavy concentration in a few positions",
            body=(f"Your best diversification score is {best_div}/100. A handful of "
                  "positions dominating the portfolio means one earnings miss moves "
                  "everything."),
            evidence={"best_diversification": best_div},
        ))
    if best_div is not None and best_div > 70:
        insights.append(Insight(
            code="well_diversified", category="strength", severity="info",
            title="Strength: well-diversified allocations",
            body=f"Diversification score {best_div}/100 — risk is genuinely spread.",
            evidence={"best_diversification": best_div},
        ))

    if traits.get("cash_pct", 0) > 60 and portfolios and len(trades) >= 1:
        oldest = min(p.created_at for p in portfolios)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        if (now - oldest).days >= 14:
            insights.append(Insight(
                code="cash_drag", category="allocation", severity="notice",
                title="Most of your money is sitting in cash",
                body=(f"{traits['cash_pct']}% of total value is uninvested. Cash "
                      "avoids drawdowns but also compounding — consider dollar-cost "
                      "averaging in."),
                evidence={"cash_pct": traits["cash_pct"]},
            ))

    # ---- knowledge gaps: XP trail + tool usage ----
    profile = get_profile(session)
    gaps: list[str] = []
    if profile.education_xp == 0:
        gaps.append("valuation metrics and investing fundamentals")
        insights.append(Insight(
            code="no_education_activity", category="knowledge", severity="notice",
            title="You have not reviewed valuation metrics yet",
            body=("No education activity recorded. The company pages show P/E, "
                  "market cap, and dividend yield — reading them before buying is "
                  "the habit that separates investing from guessing."),
            evidence={"education_xp": 0},
        ))
    if profile.research_xp == 0:
        gaps.append("company research and comparison")
    if session.scalar(select(BacktestRun.id).limit(1)) is None:
        gaps.append("strategy backtesting")
    traits["knowledge_gaps"] = gaps

    if profile.research_xp >= 100:
        insights.append(Insight(
            code="strong_researcher", category="strength", severity="info",
            title="Strength: consistent research habits",
            body=f"{profile.research_xp} research XP — you look before you leap.",
            evidence={"research_xp": profile.research_xp},
        ))

    # ---- style classification ----
    has_automation = session.scalar(select(AutomationRule.id).limit(1)) is not None
    has_plans = session.scalar(select(RecurringPlan.id).limit(1)) is not None
    dividends = any(t.kind == TransactionKind.DIVIDEND for t in txns)
    traits["uses_automation"] = has_automation
    traits["uses_recurring_plans"] = has_plans
    style = _classify_style(traits, dividends)
    strengths = [i.title.removeprefix("Strength: ") for i in insights
                 if i.category == "strength"]
    if has_automation or has_plans:
        strengths.append("systematic investing (rules/recurring plans)")

    _persist(session, username, insights, style, traits, gaps, strengths)
    return view_mentor(session, username)


def _classify_style(traits: dict, dividends: bool) -> str:
    if traits.get("trades", 0) == 0:
        return "Newcomer — no trades yet"
    if traits.get("cash_pct", 0) > 70:
        return "Cautious observer"
    if traits.get("trades_last_30d", 0) > 20:
        return "Active trader"
    if dividends and traits.get("avg_hold_days", 0) > 45:
        return "Income-focused investor"
    if (traits.get("avg_hold_days", 0) > 60
            and (traits.get("best_diversification") or 0) > 60):
        return "Long-term diversifier"
    if (traits.get("best_diversification") or 100) < 40:
        return "Concentrated conviction investor"
    return "Balanced generalist"


def _persist(session: Session, username: str, insights: list[Insight],
             style: str, traits: dict, gaps: list[str], strengths: list[str]) -> None:
    now = utcnow()
    existing = {o.code: o for o in session.scalars(
        select(MentorObservation).where(MentorObservation.username == username))}
    seen_codes = set()
    for ins in insights:
        seen_codes.add(ins.code)
        row = existing.get(ins.code)
        if row is None:
            session.add(MentorObservation(
                username=username, code=ins.code, category=ins.category,
                severity=ins.severity, title=ins.title, body=ins.body,
                evidence=json.dumps(ins.evidence), first_seen=now, last_seen=now,
            ))
        else:
            row.title, row.body = ins.title, ins.body
            row.severity, row.category = ins.severity, ins.category
            row.evidence = json.dumps(ins.evidence)
            row.last_seen = now
            row.times_seen += 1
            if row.status == ObservationStatus.RESOLVED:
                row.status = ObservationStatus.ACTIVE  # it came back
    for code, row in existing.items():
        if code not in seen_codes and row.status != ObservationStatus.RESOLVED:
            row.status = ObservationStatus.RESOLVED
            row.last_seen = now

    prof = session.get(MentorProfile, username)
    if prof is None:
        prof = MentorProfile(username=username)
        session.add(prof)
    prof.style = style
    prof.traits = json.dumps(traits)
    prof.knowledge_gaps = json.dumps(gaps)
    prof.strengths = json.dumps(sorted(set(strengths)))
    prof.updated_at = now


def view_mentor(session: Session, username: str) -> dict:
    prof = session.get(MentorProfile, username)
    rows = session.scalars(
        select(MentorObservation).where(MentorObservation.username == username)
        .order_by(MentorObservation.last_seen.desc())
    ).all()
    sev_order = {"important": 0, "notice": 1, "info": 2}
    active = sorted(
        (o for o in rows if o.status != ObservationStatus.RESOLVED),
        key=lambda o: sev_order.get(o.severity, 3),
    )
    resolved = [o for o in rows if o.status == ObservationStatus.RESOLVED]

    def obs(o: MentorObservation) -> dict:
        return {
            "id": o.id, "code": o.code, "category": o.category,
            "severity": o.severity, "title": o.title, "body": o.body,
            "evidence": json.loads(o.evidence), "status": o.status.value,
            "first_seen": o.first_seen.isoformat(), "times_seen": o.times_seen,
        }

    return {
        "profile": {
            "style": prof.style if prof else "",
            "traits": json.loads(prof.traits) if prof else {},
            "strengths": json.loads(prof.strengths) if prof else [],
            "knowledge_gaps": json.loads(prof.knowledge_gaps) if prof else [],
            "updated_at": prof.updated_at.isoformat() if prof else None,
        },
        "observations": [obs(o) for o in active],
        "resolved": [obs(o) for o in resolved],
    }


NARRATIVE_SYSTEM = (
    "You are a patient investing mentor inside a paper-trading simulator. "
    "You are given VERIFIED observations about the student computed from "
    "their real trading history. Write a short, encouraging mentor note "
    "(<=180 words) that weaves the observations together: acknowledge "
    "strengths first, then the most important issue, then one concrete next "
    "step. Do not invent facts, numbers, or tickers not present in the "
    "observations. Plain text only."
)


def narrative(runtime, mentor_view: dict) -> str:
    """LLM narration of the deterministic findings. The caller ensures a
    model is loaded; output is advisory prose only — never trades."""
    pack = {
        "style": mentor_view["profile"]["style"],
        "strengths": mentor_view["profile"]["strengths"],
        "knowledge_gaps": mentor_view["profile"]["knowledge_gaps"],
        "observations": [
            {"title": o["title"], "detail": o["body"], "severity": o["severity"]}
            for o in mentor_view["observations"][:6]
        ],
    }
    text = runtime.generate(NARRATIVE_SYSTEM, json.dumps(pack, indent=1),
                            max_tokens=400).strip()
    disclaimer = "\n\n(Educational guidance from a simulation — not financial advice.)"
    return text + disclaimer
