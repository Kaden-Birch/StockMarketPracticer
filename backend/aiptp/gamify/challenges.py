"""Daily / weekly / monthly challenges (roadmap 6.8). Assignments rotate
deterministically by period; completion is detected from XP events and real
portfolio analytics — never from trade counts."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError
from ..storage.models import (
    BacktestRun,
    BacktestStatus,
    ChallengeAssignment,
    ChallengeStatus,
    Portfolio,
    XpEvent,
)
from .service import award, gamification_enabled

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Challenge:
    id: str
    period_type: str  # DAILY | WEEKLY | MONTHLY
    name: str
    description: str
    xp: int
    check: str  # evaluator key


DAILY = [
    Challenge("daily_review_company", "DAILY", "Review a company",
              "Open any company dashboard today", 20, "xp_event:company_viewed"),
    Challenge("daily_learn_concept", "DAILY", "Learn something",
              "Read a learning suggestion from the coach", 25, "xp_event:coach_suggestion_read"),
    Challenge("daily_review_allocation", "DAILY", "Check your allocation",
              "Open a portfolio's analytics page", 20, "xp_event:analytics_reviewed"),
]
WEEKLY = [
    Challenge("weekly_diversified", "WEEKLY", "Stay diversified",
              "Have any portfolio at a diversification score of 60+", 75, "diversification_60"),
    Challenge("weekly_compare", "WEEKLY", "Compare companies",
              "Use the comparison tool this week", 50, "xp_event:companies_compared"),
    Challenge("weekly_backtest", "WEEKLY", "Test an idea",
              "Complete a backtest this week", 75, "backtest_this_period"),
]
MONTHLY = [
    Challenge("monthly_beat_benchmark", "MONTHLY", "Beat the benchmark",
              "End the month with a positive lifetime return", 150, "positive_return"),
    Challenge("monthly_diversify_70", "MONTHLY", "Diversification pro",
              "Reach a diversification score of 70+", 150, "diversification_70"),
    Challenge("monthly_strategy_goal", "MONTHLY", "Prove a strategy",
              "Complete a backtest with a positive return", 150, "winning_backtest_this_period"),
]
ALL = {c.id: c for c in DAILY + WEEKLY + MONTHLY}


def period_keys(now: datetime) -> dict[str, str]:
    iso = now.isocalendar()
    return {
        "DAILY": now.date().isoformat(),
        "WEEKLY": f"{iso.year}-W{iso.week:02d}",
        "MONTHLY": now.strftime("%Y-%m"),
    }


def _pick(pool: list[Challenge], key: str, count: int = 2) -> list[Challenge]:
    """Deterministic rotation: same period key → same challenges."""
    start = sum(ord(c) for c in key) % len(pool)
    return [(pool[(start + i) % len(pool)]) for i in range(min(count, len(pool)))]


def ensure_assignments(session: Session, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    keys = period_keys(now)
    pools = {"DAILY": DAILY, "WEEKLY": WEEKLY, "MONTHLY": MONTHLY}
    for period_type, pool in pools.items():
        key = keys[period_type]
        for challenge in _pick(pool, key):
            exists = session.scalar(
                select(ChallengeAssignment).where(
                    ChallengeAssignment.challenge_id == challenge.id,
                    ChallengeAssignment.period_key == key,
                )
            )
            if exists is None:
                session.add(ChallengeAssignment(
                    challenge_id=challenge.id, period_type=period_type, period_key=key,
                ))


def _period_start(assignment: ChallengeAssignment) -> datetime:
    key = assignment.period_key
    if assignment.period_type == "DAILY":
        return datetime.fromisoformat(key + "T00:00:00+00:00")
    if assignment.period_type == "WEEKLY":
        year, week = key.split("-W")
        return datetime.fromisocalendar(int(year), int(week), 1).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(key + "-01T00:00:00+00:00")


def _satisfied(session: Session, market, assignment: ChallengeAssignment) -> bool:
    challenge = ALL.get(assignment.challenge_id)
    if challenge is None:
        return False
    start = _period_start(assignment)
    check = challenge.check

    if check.startswith("xp_event:"):
        kind = check.split(":", 1)[1]
        count = session.scalar(
            select(func.count(XpEvent.id)).where(
                XpEvent.kind == kind, XpEvent.created_at >= start
            )
        ) or 0
        return count > 0

    if check in ("backtest_this_period", "winning_backtest_this_period"):
        runs = session.scalars(
            select(BacktestRun).where(
                BacktestRun.status == BacktestStatus.DONE,
                BacktestRun.created_at >= start,
            )
        ).all()
        if check == "backtest_this_period":
            return bool(runs)
        import json

        return any(
            (json.loads(r.results or "{}").get("total_return_pct", 0) or 0) > 0
            for r in runs
        )

    if check in ("diversification_60", "diversification_70", "positive_return"):
        from decimal import Decimal

        from ..analytics.service import diversification
        from ..portfolio.service import value_portfolio

        threshold = 70 if check == "diversification_70" else 60
        for portfolio in session.scalars(select(Portfolio)).all():
            try:
                view = value_portfolio(portfolio, market)
            except MarketDataError:
                continue
            if check == "positive_return":
                if Decimal(view["lifetime_return"]) > 0:
                    return True
            else:
                score = diversification(view)["score"]
                if score is not None and score >= threshold and len(view["holdings"]) >= 2:
                    return True
        return False

    return False


def evaluate_challenges(session: Session, market, bus) -> int:
    """Assign current-period challenges and complete any whose condition is
    met. Returns completions granted."""
    if not gamification_enabled(session):
        return 0
    ensure_assignments(session)
    session.flush()
    active = session.scalars(
        select(ChallengeAssignment).where(
            ChallengeAssignment.status == ChallengeStatus.ACTIVE
        )
    ).all()
    now = datetime.now(timezone.utc)
    keys = period_keys(now)
    completed = 0
    for assignment in active:
        if assignment.period_key != keys.get(assignment.period_type):
            continue  # expired period — leave inactive history as-is
        if _satisfied(session, market, assignment):
            challenge = ALL[assignment.challenge_id]
            assignment.status = ChallengeStatus.COMPLETED
            assignment.completed_at = now
            award(session, bus, "challenge", f"challenge:{challenge.id}",
                  challenge.xp, f"Challenge: {challenge.name}")
            if bus is not None:
                bus.publish(
                    "challenge",
                    {"id": challenge.id, "name": challenge.name,
                     "description": f"{challenge.description} (+{challenge.xp} XP)"},
                    session=session,
                )
            completed += 1
    return completed


def assignments_view(session: Session) -> list[dict]:
    ensure_assignments(session)
    session.flush()
    keys = period_keys(datetime.now(timezone.utc))
    out = []
    for assignment in session.scalars(
        select(ChallengeAssignment).order_by(ChallengeAssignment.created_at.desc()).limit(30)
    ).all():
        challenge = ALL.get(assignment.challenge_id)
        if challenge is None:
            continue
        out.append({
            "id": assignment.id,
            "challenge_id": challenge.id,
            "name": challenge.name,
            "description": challenge.description,
            "period_type": assignment.period_type,
            "period_key": assignment.period_key,
            "current": assignment.period_key == keys.get(assignment.period_type),
            "xp": challenge.xp,
            "status": assignment.status.value,
            "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
        })
    return out
