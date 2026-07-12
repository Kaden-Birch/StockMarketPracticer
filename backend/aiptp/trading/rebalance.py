"""Rebalancing: compute the order set that moves a portfolio to target
weights, optionally executing it (sells first so buys are funded)."""

from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..marketdata.service import MarketDataService
from ..storage.models import OrderSide, OrderType, Origin, Portfolio
from .engine import CASH_PLACES, QTY_PLACES, TradingError, place_order

MIN_TRADE = Decimal("1.00")  # ignore dust adjustments below this value


def plan_rebalance(
    portfolio: Portfolio,
    targets: dict[str, Decimal],
    market: MarketDataService,
) -> dict[str, Any]:
    """Compute current vs target weights and the trades needed. Target
    weights are percentages of total portfolio value; the unallocated
    remainder stays in cash."""
    total_pct = sum(targets.values())
    if total_pct > 100:
        raise TradingError(f"Target weights sum to {total_pct}%, which exceeds 100%")
    if any(w < 0 for w in targets.values()):
        raise TradingError("Target weights must be non-negative")

    symbols = sorted({s.upper() for s in targets} | {h.symbol for h in portfolio.holdings if h.quantity > 0})
    quotes = market.get_quotes(symbols) if symbols else {}
    fx = {
        s: market.get_fx_rate(q.currency, portfolio.currency) for s, q in quotes.items()
    }
    local_price = {s: quotes[s].price * fx[s] for s in quotes}

    position_value = {
        h.symbol: (h.quantity * local_price[h.symbol]).quantize(CASH_PLACES)
        for h in portfolio.holdings
        if h.quantity > 0
    }
    total_value = portfolio.cash_balance + sum(position_value.values(), Decimal("0"))

    trades = []
    for symbol in symbols:
        target_pct = Decimal(str(targets.get(symbol, targets.get(symbol.upper(), 0))))
        target_value = (total_value * target_pct / 100).quantize(CASH_PLACES)
        current_value = position_value.get(symbol, Decimal("0"))
        delta = target_value - current_value
        if abs(delta) < MIN_TRADE:
            continue
        price = local_price[symbol]
        if delta < 0:
            qty = (-delta / price).quantize(QTY_PLACES, rounding=ROUND_DOWN)
            held = next(
                (h.quantity for h in portfolio.holdings if h.symbol == symbol), Decimal("0")
            )
            qty = min(qty, held)
            if qty <= 0:
                continue
            trades.append(
                {"symbol": symbol, "side": "SELL", "quantity": str(qty),
                 "est_value": str((qty * price).quantize(CASH_PLACES))}
            )
        else:
            trades.append(
                {"symbol": symbol, "side": "BUY", "notional": str(delta),
                 "est_value": str(delta)}
            )
    # Sells first so the buys are funded.
    trades.sort(key=lambda t: 0 if t["side"] == "SELL" else 1)
    return {
        "total_value": str(total_value.quantize(CASH_PLACES)),
        "cash_balance": str(portfolio.cash_balance),
        "current_weights": {
            s: str((v / total_value * 100).quantize(Decimal("0.01"))) if total_value else "0"
            for s, v in position_value.items()
        },
        "targets": {s.upper(): str(Decimal(str(w))) for s, w in targets.items()},
        "trades": trades,
    }


def execute_rebalance(
    session: Session,
    portfolio: Portfolio,
    plan: dict[str, Any],
    market: MarketDataService,
    origin: Origin = Origin.MANUAL,
) -> list[dict[str, Any]]:
    results = []
    for trade in plan["trades"]:
        symbol = trade["symbol"]
        quote = market.get_quote(symbol)
        fx = market.get_fx_rate(quote.currency, portfolio.currency)
        try:
            order, txn = place_order(
                session,
                portfolio,
                symbol=symbol,
                side=OrderSide(trade["side"]),
                type_=OrderType.MARKET,
                quantity=Decimal(trade["quantity"]) if "quantity" in trade else None,
                notional=Decimal(trade["notional"]) if "notional" in trade else None,
                origin=origin,
                current_price=quote.price,
                fx_rate=fx,
                quote_currency=quote.currency,
            )
            results.append({"symbol": symbol, "side": trade["side"],
                            "status": order.status.value, "order_id": order.id})
        except TradingError as exc:
            results.append({"symbol": symbol, "side": trade["side"],
                            "status": "REJECTED", "error": str(exc)})
    return results
