"""Pending-order trigger evaluation — pure functions, shared by the live
watcher and (later) the backtest engine so both behave identically."""

from decimal import Decimal

from ..storage.models import Order, OrderSide, OrderType


def limit_satisfied(order: Order, price: Decimal) -> bool:
    if order.side == OrderSide.BUY:
        return price <= order.limit_price
    return price >= order.limit_price


def stop_triggered(order: Order, price: Decimal) -> bool:
    if order.side == OrderSide.BUY:
        return price >= order.stop_price
    return price <= order.stop_price


def trailing_threshold(order: Order) -> Decimal:
    """Current trigger price implied by the watermark and trail settings."""
    wm = order.watermark
    if order.trail_amount is not None:
        offset = order.trail_amount
    else:
        offset = wm * order.trail_percent / Decimal("100")
    return wm - offset if order.side == OrderSide.SELL else wm + offset


def evaluate(order: Order, price: Decimal) -> tuple[bool, Decimal | None]:
    """Return (should_fill, fill_price). May mutate order state that must be
    persisted by the caller: stop_triggered (STOP_LIMIT) and watermark
    (TRAILING_STOP)."""
    if order.type == OrderType.MARKET:
        return True, price
    if order.type == OrderType.LIMIT:
        if limit_satisfied(order, price):
            # Fill at the better of limit and market, from the trader's side.
            if order.side == OrderSide.BUY:
                return True, min(price, order.limit_price)
            return True, max(price, order.limit_price)
        return False, None
    if order.type == OrderType.STOP:
        if stop_triggered(order, price):
            return True, price
        return False, None
    if order.type == OrderType.TRAILING_STOP:
        if order.watermark is None:
            order.watermark = price
        # Ratchet the watermark in the favorable direction only.
        if order.side == OrderSide.SELL:
            order.watermark = max(order.watermark, price)
        else:
            order.watermark = min(order.watermark, price)
        threshold = trailing_threshold(order)
        if order.side == OrderSide.SELL and price <= threshold:
            return True, price
        if order.side == OrderSide.BUY and price >= threshold:
            return True, price
        return False, None
    if order.type == OrderType.STOP_LIMIT:
        if not order.stop_triggered:
            if stop_triggered(order, price):
                order.stop_triggered = True
            else:
                return False, None
        if limit_satisfied(order, price):
            if order.side == OrderSide.BUY:
                return True, min(price, order.limit_price)
            return True, max(price, order.limit_price)
        return False, None
    raise ValueError(f"Unsupported order type: {order.type}")
