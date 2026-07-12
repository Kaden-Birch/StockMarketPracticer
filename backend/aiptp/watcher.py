"""Price watch scheduler: polls quotes for every symbol the platform cares
about (open positions + pending orders), evaluates pending orders, and pushes
quote/fill events to WebSocket clients. Runs as a plain APScheduler job in a
worker thread; in Server Mode this is what keeps the platform trading 24/7
with nobody connected (PRD §4)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .core.events import EventBus
from .marketdata.base import MarketDataError
from .marketdata.service import MarketDataService
from .storage.models import Holding, Order, OrderStatus
from .trading.engine import evaluate_pending_orders

log = logging.getLogger(__name__)


def watched_symbols(session: Session) -> set[str]:
    pending = session.scalars(
        select(Order.symbol).where(Order.status == OrderStatus.PENDING).distinct()
    ).all()
    held = session.scalars(select(Holding.symbol).where(Holding.quantity > 0).distinct()).all()
    return set(pending) | set(held)


def run_watch_cycle(
    session_factory: sessionmaker, market: MarketDataService, bus: EventBus
) -> None:
    with session_factory() as session:
        symbols = watched_symbols(session)
        if not symbols:
            return
        try:
            quotes = market.get_quotes(sorted(symbols))
        except MarketDataError as exc:
            log.warning("Watch cycle quote fetch failed: %s", exc)
            return

        bus.publish(
            "quotes",
            {
                s: {"price": str(q.price), "previous_close": str(q.previous_close or ""),
                    "as_of": q.as_of.isoformat()}
                for s, q in quotes.items()
            },
        )

        prices = {s: q.price for s, q in quotes.items()}
        fills = evaluate_pending_orders(session, prices)
        session.commit()
        for txn in fills:
            log.info("Filled order %s: %s %s %s @ %s",
                     txn.order_id, txn.side.value, txn.quantity, txn.symbol, txn.price)
            bus.publish(
                "order_filled",
                {
                    "portfolio_id": txn.portfolio_id,
                    "order_id": txn.order_id,
                    "symbol": txn.symbol,
                    "side": txn.side.value,
                    "quantity": str(txn.quantity),
                    "price": str(txn.price),
                    "origin": txn.origin.value,
                },
            )
