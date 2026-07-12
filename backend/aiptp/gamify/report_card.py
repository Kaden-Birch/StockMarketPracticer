"""Portfolio report card (roadmap 6.9): periodic letter-grade evaluation
computed deterministically from real analytics."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics.service import diversification, risk_metrics, trade_records, value_history
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import AutomationRule, Portfolio, RecurringPlan, Strategy, XpEvent

GRADES = ["F", "D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]


def _grade(score: float) -> str:
    """score 0..1 → letter."""
    idx = max(0, min(len(GRADES) - 1, int(round(score * (len(GRADES) - 1)))))
    return GRADES[idx]


def report_card(session: Session, portfolio: Portfolio, market: MarketDataService) -> dict:
    from ..portfolio.service import value_portfolio

    view = value_portfolio(portfolio, market)
    div = diversification(view)
    records = trade_records(session, portfolio)
    try:
        points = value_history(session, portfolio, market, "6M")["points"]
        risk = risk_metrics(points)
    except MarketDataError:
        points, risk = [], {}

    subjects: dict[str, dict] = {}

    # Diversification: HHI score maps directly.
    div_score = (div["score"] or 0) / 100
    subjects["diversification"] = {
        "grade": _grade(div_score),
        "detail": f"Diversification score {div['score'] if div['score'] is not None else '—'} across "
                  f"{len(view['holdings'])} positions plus cash.",
    }

    # Risk management: drawdown-based (0% dd -> 1.0, -30%+ -> 0).
    dd = risk.get("max_drawdown")
    risk_score = 0.5 if dd is None else max(0.0, 1 + (dd / 30))
    subjects["risk_management"] = {
        "grade": _grade(min(1.0, risk_score)),
        "detail": f"Max drawdown {dd}%" if dd is not None else "Not enough history yet.",
    }

    # Research: research/education XP earned in the last 30 days (cap 200).
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_xp = session.scalar(
        select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
            XpEvent.category.in_(["research", "education"]),
            XpEvent.created_at >= month_ago,
        )
    ) or 0
    subjects["research"] = {
        "grade": _grade(min(1.0, recent_xp / 200)),
        "detail": f"{recent_xp} research/education XP earned in the last 30 days.",
    }

    # Returns: lifetime return vs starting balance (-10%..+10% -> 0..1).
    lifetime_pct = float(
        Decimal(view["lifetime_return"]) / portfolio.starting_balance * 100
    ) if portfolio.starting_balance else 0.0
    subjects["returns"] = {
        "grade": _grade(max(0.0, min(1.0, (lifetime_pct + 10) / 20))),
        "detail": f"Lifetime return {lifetime_pct:.2f}%.",
    }

    # Patience: average holding period (60+ days -> 1.0). No closed trades
    # yet reads as neutral-good (nothing impulsive on record).
    avg_days = records.get("avg_holding_days")
    patience_score = 0.7 if avg_days is None else min(1.0, avg_days / 60)
    subjects["patience"] = {
        "grade": _grade(patience_score),
        "detail": f"Average holding period {avg_days} days."
                  if avg_days is not None else "No closed trades yet.",
    }

    # Strategy discipline: uses plans/rules/strategies instead of ad-hoc only.
    tools = 0
    tools += 1 if session.scalar(select(func.count(RecurringPlan.id)).where(
        RecurringPlan.portfolio_id == portfolio.id)) else 0
    tools += 1 if session.scalar(select(func.count(AutomationRule.id)).where(
        AutomationRule.portfolio_id == portfolio.id)) else 0
    tools += 1 if session.scalar(select(func.count(Strategy.id))) else 0
    subjects["strategy_discipline"] = {
        "grade": _grade(0.3 + tools * 0.7 / 3),
        "detail": f"Using {tools}/3 planning tools (recurring plans, automation rules, strategies).",
    }

    overall = _grade(
        sum(GRADES.index(s["grade"]) / (len(GRADES) - 1) for s in subjects.values())
        / len(subjects)
    )
    return {
        "portfolio_id": portfolio.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "subjects": subjects,
        "note": "Grades are computed from your real portfolio data and refresh on demand.",
    }
