"""Recurring purchase (DCA) execution. A scheduler job runs due plans as
market notional buys at the current real price.

Deviation from the architecture note: runs missed while the app was offline
execute at the next startup at the then-current price (flagged via
last_run_at drift), not backfilled at the historical scheduled-time price.
Historical backfill would require intraday history replay and arrives with
the backtest engine (M5)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..storage.models import Cadence, OrderSide, OrderType, Origin, Portfolio, RecurringPlan
from .engine import TradingError, place_order

log = logging.getLogger(__name__)

_CADENCE_DELTA = {
    Cadence.DAILY: timedelta(days=1),
    Cadence.WEEKLY: timedelta(weeks=1),
    Cadence.MONTHLY: timedelta(days=30),
}


def advance(plan: RecurringPlan, now: datetime) -> None:
    """Move next_run_at forward past `now`, preserving the original cadence
    anchor so a late run doesn't shift the schedule."""
    delta = _CADENCE_DELTA[plan.cadence]
    next_run = plan.next_run_at
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)
    while next_run <= now:
        next_run += delta
    plan.next_run_at = next_run


def run_due_plans(session: Session, market: MarketDataService, bus=None) -> int:
    now = datetime.now(timezone.utc)
    due = session.scalars(
        select(RecurringPlan).where(
            RecurringPlan.enabled == True,  # noqa: E712
            RecurringPlan.next_run_at <= now,
        )
    ).all()
    executed = 0
    for plan in due:
        portfolio = session.get(Portfolio, plan.portfolio_id)
        if portfolio is None:
            continue
        try:
            quote = market.get_quote(plan.symbol)
            fx = market.get_fx_rate(quote.currency, portfolio.currency)
            order, txn = place_order(
                session,
                portfolio,
                symbol=plan.symbol,
                side=OrderSide.BUY,
                type_=OrderType.MARKET,
                notional=plan.amount,
                origin=Origin.AUTOMATION,
                current_price=quote.price,
                fx_rate=fx,
                quote_currency=quote.currency,
            )
        except (MarketDataError, TradingError) as exc:
            # Skip this cycle (e.g. insufficient cash); try again next cadence
            # rather than hammering every scheduler tick.
            log.warning("Recurring plan %s (%s) skipped: %s", plan.id, plan.symbol, exc)
            advance(plan, now)
            continue
        plan.last_run_at = now
        plan.run_count += 1
        advance(plan, now)
        executed += 1
        if bus is not None and txn is not None:
            bus.publish(
                "recurring_executed",
                {
                    "portfolio_id": portfolio.id,
                    "plan_id": plan.id,
                    "symbol": plan.symbol,
                    "quantity": str(txn.quantity),
                    "price": str(txn.price),
                },
                session=session,
            )
    return executed


def run_recurring_cycle(session_factory, market: MarketDataService, bus=None) -> None:
    with session_factory() as session:
        count = run_due_plans(session, market, bus)
        session.commit()
        if count:
            log.info("Executed %d recurring purchase(s)", count)
