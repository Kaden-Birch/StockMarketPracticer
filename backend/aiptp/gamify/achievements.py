"""Achievement catalog and evaluator (roadmap 6.7). Definitions reward
meaningful progress — learning, discipline, diversification, longevity —
never trade counts."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError
from ..storage.models import (
    BacktestRun,
    BacktestStatus,
    EarnedAchievement,
    Holding,
    OrderSide,
    Portfolio,
    Strategy,
    Transaction,
    TransactionKind,
    XpEvent,
)
from .service import award, gamification_enabled

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    category: str  # beginner | education | portfolio | strategy | long_term
    description: str
    xp: int


CATALOG: list[Achievement] = [
    Achievement("first_investment", "First Investment", "beginner",
                "Buy your first security", 50),
    Achievement("first_profit", "First Profit", "beginner",
                "Close a position with a realized gain", 75),
    Achievement("first_dividend", "First Dividend", "beginner",
                "Receive your first dividend payment", 75),
    Achievement("researcher_10", "Curious Mind", "education",
                "Review 10 companies", 100),
    Achievement("researcher_50", "Deep Researcher", "education",
                "Review 50 companies", 250),
    Achievement("student_10", "Student of the Market", "education",
                "Read 10 learning suggestions from the coach", 150),
    Achievement("diversified", "Diversified", "portfolio",
                "Reach a diversification score of 60+ with 5+ positions", 150),
    Achievement("benchmark_beater", "Benchmark Beater", "portfolio",
                "Have a portfolio worth more than its benchmark-tracked start", 200),
    Achievement("crash_survivor", "Crash Survivor", "portfolio",
                "Recover to a new high after a 10%+ drawdown", 250),
    Achievement("first_strategy", "Strategist", "strategy",
                "Create your first strategy", 100),
    Achievement("first_backtest", "Time Traveler", "strategy",
                "Complete a backtest", 100),
    Achievement("winning_strategy", "Proven Edge", "strategy",
                "Backtest a strategy to a positive return with 5+ closed trades", 200),
    Achievement("year_holder", "Long-Term Thinker", "long_term",
                "Hold a position for a full year", 300),
    Achievement("steady_hand", "Steady Hand", "long_term",
                "Keep average holding period above 30 days across 10+ closed trades", 200),
]

CATALOG_BY_ID = {a.id: a for a in CATALOG}


def _earned_ids(session: Session) -> set[str]:
    return set(session.scalars(select(EarnedAchievement.achievement_id)).all())


_XP_CATEGORY = {
    "beginner": "portfolio",
    "education": "education",
    "portfolio": "portfolio",
    "strategy": "research",
    "long_term": "portfolio",
}


def _grant(session: Session, bus, achievement: Achievement,
           portfolio_id: str | None = None) -> None:
    session.add(EarnedAchievement(achievement_id=achievement.id, portfolio_id=portfolio_id))
    award(session, bus, _XP_CATEGORY[achievement.category],
          f"achievement:{achievement.id}", achievement.xp,
          f"Achievement: {achievement.name}", portfolio_id)
    if bus is not None:
        bus.publish(
            "achievement",
            {"id": achievement.id, "name": achievement.name,
             "description": f"{achievement.description} (+{achievement.xp} XP)",
             "portfolio_id": portfolio_id},
            session=session,
        )
    log.info("Achievement earned: %s", achievement.id)


def evaluate_achievements(session: Session, market, bus) -> int:
    """Check every unearned achievement against current state. Idempotent —
    earned achievements are unique-indexed. Returns number granted."""
    if not gamification_enabled(session):
        return 0
    earned = _earned_ids(session)
    granted = 0

    def check(aid: str) -> bool:
        return aid not in earned and aid in CATALOG_BY_ID

    trades = session.scalar(
        select(func.count(Transaction.id)).where(Transaction.kind == TransactionKind.TRADE)
    ) or 0
    if check("first_investment") and trades > 0:
        first = session.scalar(
            select(Transaction).where(Transaction.kind == TransactionKind.TRADE).limit(1)
        )
        _grant(session, bus, CATALOG_BY_ID["first_investment"], first.portfolio_id)
        granted += 1

    if check("first_profit"):
        row = session.scalar(
            select(Transaction).where(Transaction.realized_pnl > 0).limit(1)
        )
        if row is not None:
            _grant(session, bus, CATALOG_BY_ID["first_profit"], row.portfolio_id)
            granted += 1

    if check("first_dividend"):
        row = session.scalar(
            select(Transaction).where(Transaction.kind == TransactionKind.DIVIDEND).limit(1)
        )
        if row is not None:
            _grant(session, bus, CATALOG_BY_ID["first_dividend"], row.portfolio_id)
            granted += 1

    if check("researcher_10") or check("researcher_50"):
        distinct_reviews = session.scalar(
            select(func.count(func.distinct(XpEvent.reason))).where(
                XpEvent.kind == "company_viewed"
            )
        ) or 0
        if check("researcher_10") and distinct_reviews >= 10:
            _grant(session, bus, CATALOG_BY_ID["researcher_10"])
            granted += 1
        if check("researcher_50") and distinct_reviews >= 50:
            _grant(session, bus, CATALOG_BY_ID["researcher_50"])
            granted += 1

    if check("student_10"):
        reads = session.scalar(
            select(func.count(XpEvent.id)).where(XpEvent.kind == "coach_suggestion_read")
        ) or 0
        if reads >= 10:
            _grant(session, bus, CATALOG_BY_ID["student_10"])
            granted += 1

    if check("first_strategy"):
        if (session.scalar(select(func.count(Strategy.id))) or 0) > 0:
            _grant(session, bus, CATALOG_BY_ID["first_strategy"])
            granted += 1

    if check("first_backtest") or check("winning_strategy"):
        runs = session.scalars(
            select(BacktestRun).where(BacktestRun.status == BacktestStatus.DONE)
        ).all()
        if check("first_backtest") and runs:
            _grant(session, bus, CATALOG_BY_ID["first_backtest"])
            granted += 1
        if check("winning_strategy"):
            import json

            for run in runs:
                results = json.loads(run.results or "{}")
                if (results.get("total_return_pct", 0) or 0) > 0 and \
                        (results.get("closed_trades", 0) or 0) >= 5:
                    _grant(session, bus, CATALOG_BY_ID["winning_strategy"])
                    granted += 1
                    break

    # portfolio-state achievements (need live valuation)
    portfolios = session.scalars(select(Portfolio)).all()
    for portfolio in portfolios:
        if not (check("diversified") or check("benchmark_beater")
                or check("year_holder") or check("crash_survivor")
                or check("steady_hand")):
            break
        try:
            from ..analytics.service import diversification, trade_records
            from ..portfolio.service import value_portfolio

            view = value_portfolio(portfolio, market)
        except MarketDataError:
            continue
        if check("diversified"):
            div = diversification(view)
            positions = len([h for h in view["holdings"]])
            if div["score"] is not None and div["score"] >= 60 and positions >= 5:
                _grant(session, bus, CATALOG_BY_ID["diversified"], portfolio.id)
                earned.add("diversified")
                granted += 1
        if check("benchmark_beater"):
            from decimal import Decimal

            if Decimal(view["lifetime_return"]) > 0 and trades > 0:
                _grant(session, bus, CATALOG_BY_ID["benchmark_beater"], portfolio.id)
                earned.add("benchmark_beater")
                granted += 1
        if check("year_holder"):
            year_ago = datetime.now(timezone.utc) - timedelta(days=365)
            old_lot = session.scalar(
                select(Holding)
                .join(Holding.lots)
                .where(Holding.portfolio_id == portfolio.id, Holding.quantity > 0)
                .limit(1)
            )
            if old_lot is not None:
                oldest = min(
                    (lot.acquired_at.replace(tzinfo=timezone.utc)
                     if lot.acquired_at.tzinfo is None else lot.acquired_at
                     for lot in old_lot.lots if lot.quantity_remaining > 0),
                    default=None,
                )
                if oldest is not None and oldest <= year_ago:
                    _grant(session, bus, CATALOG_BY_ID["year_holder"], portfolio.id)
                    earned.add("year_holder")
                    granted += 1
        if check("steady_hand"):
            records = trade_records(session, portfolio)
            if (records["closed_trades"] or 0) >= 10 and \
                    (records["avg_holding_days"] or 0) > 30:
                _grant(session, bus, CATALOG_BY_ID["steady_hand"], portfolio.id)
                earned.add("steady_hand")
                granted += 1
        if check("crash_survivor"):
            try:
                from ..analytics.service import value_history

                points = value_history(session, portfolio, market, "1Y")["points"]
            except MarketDataError:
                points = []
            peak = trough_after_peak = None
            recovered = False
            for p in points:
                v = p["value"]
                if peak is None or v > peak:
                    if (peak is not None and trough_after_peak is not None
                            and peak > 0 and (trough_after_peak - peak) / peak <= -0.10):
                        recovered = True  # new high after a 10%+ drawdown
                        break
                    peak, trough_after_peak = v, None
                elif trough_after_peak is None or v < trough_after_peak:
                    trough_after_peak = v
            if recovered:
                _grant(session, bus, CATALOG_BY_ID["crash_survivor"], portfolio.id)
                earned.add("crash_survivor")
                granted += 1
    return granted
