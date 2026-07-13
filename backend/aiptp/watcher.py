"""Price watch scheduler: polls quotes for every symbol the platform cares
about (open positions + pending orders), evaluates pending orders, and pushes
quote/fill events to WebSocket clients. Runs as a plain APScheduler job in a
worker thread; in Server Mode this is what keeps the platform trading 24/7
with nobody connected (PRD §4)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from decimal import Decimal

from .core.events import EventBus
from .marketdata.base import MarketDataError
from .marketdata.service import MarketDataService
from .storage.models import Holding, Order, OrderStatus, Portfolio
from .trading.engine import evaluate_pending_orders

log = logging.getLogger(__name__)


def watched_symbols(session: Session) -> set[str]:
    pending = session.scalars(
        select(Order.symbol).where(Order.status == OrderStatus.PENDING).distinct()
    ).all()
    held = session.scalars(select(Holding.symbol).where(Holding.quantity > 0).distinct()).all()
    out = set(pending) | set(held)
    # symbols referenced by enabled automation rules (event-driven triggers)
    import json

    from .automation.conditions import referenced_symbols
    from .storage.models import AutomationRule

    for trigger_json in session.scalars(
        select(AutomationRule.trigger).where(AutomationRule.enabled == True)  # noqa: E712
    ):
        try:
            out |= referenced_symbols(json.loads(trigger_json))
        except (json.JSONDecodeError, ValueError, StopIteration):
            continue
    return out


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
        # FX rates for pending orders whose security trades in a different
        # currency than its portfolio.
        pending_pairs = session.execute(
            select(Order.symbol, Portfolio.currency)
            .join(Portfolio, Portfolio.id == Order.portfolio_id)
            .where(Order.status == OrderStatus.PENDING, Order.symbol.in_(list(prices)))
            .distinct()
        ).all()
        fx_rates: dict[str, "Decimal"] = {}
        quote_currencies = {s: q.currency for s, q in quotes.items()}
        for symbol, portfolio_ccy in pending_pairs:
            quote = quotes.get(symbol)
            if quote is None or quote.currency == portfolio_ccy:
                continue
            try:
                fx_rates[f"{symbol}:{portfolio_ccy}"] = market.get_fx_rate(
                    quote.currency, portfolio_ccy
                )
            except MarketDataError as exc:
                log.warning("FX fetch failed for %s->%s: %s", quote.currency, portfolio_ccy, exc)
                prices.pop(symbol, None)  # don't fill at a wrong rate

        fills = evaluate_pending_orders(session, prices, fx_rates, quote_currencies)
        session.commit()

        # Modules (automation, ...) react to this instead of being called
        # directly — the core publishes, subscribers decide (roadmap 6.11.4).
        bus.publish(
            "watch.quotes",
            {
                "prices": {s: str(p) for s, p in prices.items()},
                "previous_closes": {
                    s: str(q.previous_close)
                    for s, q in quotes.items()
                    if q.previous_close
                },
            },
        )
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
