"""Career mode (roadmap 8.3) and advanced challenges (8.5).

Rank ladder: Intern Investor → Retail Investor → Portfolio Manager →
Fund Manager → Institutional Investor. Each rank has objectives evaluated
deterministically from real platform state (trades, valuations, mandates,
scenario results). Completed objective codes persist append-only; the rank
advances when every objective of the current rank is done."""

import json
from datetime import timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics.service import diversification, risk_metrics, value_history
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..scenario.catalog import SCENARIOS
from ..storage.models import (
    CareerState,
    Portfolio,
    ScenarioSession,
    Transaction,
    TransactionKind,
    XpEvent,
    utcnow,
)
from . import mandates as mandates_mod

RANKS = [
    "Intern Investor",
    "Retail Investor",
    "Portfolio Manager",
    "Fund Manager",
    "Institutional Investor",
]

# objective code -> (rank it belongs to, label, description)
OBJECTIVES: dict[str, tuple[int, str, str]] = {
    "first_trades": (0, "Place 5 trades",
                     "Get hands-on: execute at least 5 trades."),
    "learn_basics": (0, "Start learning",
                     "Earn any education or research XP (read a company page, "
                     "compare stocks, review analytics)."),
    "diversify": (1, "Build a diversified portfolio",
                  "Reach a diversification score of 50+ on any portfolio."),
    "manage_risk": (1, "Review your risk",
                    "Study a portfolio's analytics (risk metrics reviewed)."),
    "positive_return": (1, "Prove profitability",
                        "A portfolio at least 30 days old with a positive "
                        "lifetime return."),
    "follow_mandate": (2, "Run a mandated portfolio",
                       "Adopt a mandate (retirement/growth/dividend/technology) "
                       "and be fully compliant."),
    "beat_benchmark": (2, "Beat the market",
                       "Outperform your benchmark over the same period "
                       "(portfolio 30+ days old)."),
    "scale_up": (2, "Scale to $500k",
                 "Manage at least $500,000 across your live portfolios."),
    "survive_recession": (3, "Survive a recession",
                          "Complete a crash scenario (dot-com or 2008) beating "
                          "the market's return through the same period."),
    "protect_investors": (3, "Protect your investors",
                          "No live portfolio (30+ days old) with a drawdown "
                          "worse than -30%."),
    "billion_dollar": (4, "Manage a billion",
                       "Reach $1,000,000,000 under management."),
    "crash_recovery": (4, "Recover from a crash",
                       "Bring a portfolio that was down 20%+ back to a "
                       "positive lifetime return."),
}

# The roadmap-8.5 advanced challenges, surfaced separately on the career page.
ADVANCED_CHALLENGES = ("beat_benchmark", "survive_recession", "billion_dollar",
                      "crash_recovery")


def _portfolio_stats(session: Session, market: MarketDataService,
                     username: str) -> dict:
    """One pass over live portfolios collecting everything objectives need."""
    portfolios = session.scalars(select(Portfolio).where(
        Portfolio.owner == username,
        Portfolio.scenario_session_id.is_(None),
    )).all()
    stats = {
        "total_value": Decimal("0"),
        "best_diversification": None,
        "any_positive_30d": False,
        "beat_benchmark": False,
        "worst_drawdown_ok": True,
        "crash_recovery": False,
        "mandate_compliant": False,
    }
    now = utcnow()
    for p in portfolios:
        try:
            view = value_portfolio(p, market)
        except MarketDataError:
            continue
        stats["total_value"] += Decimal(view["total_value"])
        d = diversification(view).get("score")
        if d is not None and (stats["best_diversification"] is None
                              or d > stats["best_diversification"]):
            stats["best_diversification"] = d
        created = p.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).days
        lifetime = Decimal(view["lifetime_return"])
        if age >= 30 and lifetime > 0:
            stats["any_positive_30d"] = True
        if p.mandate:
            comp = mandates_mod.compliance(session, p, market)
            if comp.get("compliant") is True:
                stats["mandate_compliant"] = True
        if age >= 30:
            try:
                points = value_history(session, p, market, "1Y")["points"]
                risk = risk_metrics(points)
            except MarketDataError:
                points, risk = [], {}
            dd = risk.get("max_drawdown")
            if dd is not None and dd <= -30:
                stats["worst_drawdown_ok"] = False
            if dd is not None and dd <= -20 and lifetime > 0:
                stats["crash_recovery"] = True
            if len(points) >= 5:
                first, last = points[0], points[-1]
                if first["benchmark_close"] and last["benchmark_close"]:
                    port_r = last["value"] / first["value"] - 1
                    bench_r = last["benchmark_close"] / first["benchmark_close"] - 1
                    if port_r > bench_r:
                        stats["beat_benchmark"] = True
    return stats


def evaluate(session: Session, market: MarketDataService, username: str) -> dict:
    """Evaluate all objectives, persist newly completed codes, advance rank
    when the current rank's objectives are all done. Caller commits."""
    state = session.get(CareerState, username)
    if state is None:
        state = CareerState(username=username, rank=0, completed="[]")
        session.add(state)
    done: set[str] = set(json.loads(state.completed))

    trades = session.scalar(
        select(func.count()).select_from(Transaction)
        .join(Portfolio, Portfolio.id == Transaction.portfolio_id)
        .where(Portfolio.owner == username,
               Transaction.kind == TransactionKind.TRADE)
    ) or 0
    has_learning_xp = session.scalar(select(XpEvent.id).where(
        XpEvent.category.in_(["education", "research"])).limit(1)) is not None
    has_risk_review = session.scalar(select(XpEvent.id).where(
        XpEvent.kind == "analytics_reviewed").limit(1)) is not None

    stats = _portfolio_stats(session, market, username)

    # survive_recession: a completed brutal scenario where the player beat
    # that scenario's full-period market return.
    survived = False
    for sess in session.scalars(select(ScenarioSession).where(
            ScenarioSession.username == username,
            ScenarioSession.completed == True)):  # noqa: E712
        scenario = SCENARIOS.get(sess.scenario_id)
        if scenario is None or scenario.difficulty != "brutal":
            continue
        points = json.loads(sess.value_points)
        if not points:
            continue
        final = Decimal(points[-1][1])
        start = Decimal(scenario.starting_cash)
        player_r = (final - start) / start
        try:
            bars = market.get_history_window(
                scenario.benchmark, scenario.start_ts, scenario.end_ts).bars
            bench_r = (Decimal(str(bars[-1].close)) / Decimal(str(bars[0].close))) - 1
        except MarketDataError:
            continue
        if player_r > bench_r:
            survived = True
            break

    checks = {
        "first_trades": trades >= 5,
        "learn_basics": has_learning_xp,
        "diversify": (stats["best_diversification"] or 0) >= 50,
        "manage_risk": has_risk_review,
        "positive_return": stats["any_positive_30d"],
        "follow_mandate": stats["mandate_compliant"],
        "beat_benchmark": stats["beat_benchmark"],
        "scale_up": stats["total_value"] >= Decimal("500000"),
        "survive_recession": survived,
        "protect_investors": stats["worst_drawdown_ok"] and trades >= 5,
        "billion_dollar": stats["total_value"] >= Decimal("1000000000"),
        "crash_recovery": stats["crash_recovery"],
    }
    for code, ok in checks.items():
        if ok:
            done.add(code)  # objectives never un-complete

    # rank advances while every objective at the current rank is done
    while state.rank < len(RANKS) - 1:
        rank_objectives = [c for c, (r, _, _) in OBJECTIVES.items()
                           if r == state.rank]
        if all(c in done for c in rank_objectives):
            state.rank += 1
        else:
            break

    state.completed = json.dumps(sorted(done))
    state.updated_at = utcnow()
    return view(session, username, extra={"progress": {
        "trades": trades,
        "total_value": str(stats["total_value"].quantize(Decimal("0.01"))),
        "best_diversification": stats["best_diversification"],
    }})


def view(session: Session, username: str, extra: dict | None = None) -> dict:
    state = session.get(CareerState, username)
    rank = state.rank if state else 0
    done = set(json.loads(state.completed)) if state else set()
    objectives = [
        {"code": code, "rank": r, "rank_name": RANKS[r], "label": label,
         "description": desc, "done": code in done,
         "current": r == rank}
        for code, (r, label, desc) in OBJECTIVES.items()
    ]
    out = {
        "rank": rank,
        "rank_name": RANKS[rank],
        "next_rank": RANKS[rank + 1] if rank < len(RANKS) - 1 else None,
        "ladder": RANKS,
        "objectives": objectives,
        "challenges": [o for o in objectives if o["code"] in ADVANCED_CHALLENGES],
        "updated_at": state.updated_at.isoformat() if state else None,
    }
    out.update(extra or {})
    return out
