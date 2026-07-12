from decimal import Decimal

from aiptp.storage.models import Order, OrderSide, OrderType
from aiptp.trading.triggers import evaluate


def make_order(side, type_, limit=None, stop=None) -> Order:
    return Order(
        portfolio_id="p",
        symbol="TEST",
        side=side,
        type=type_,
        quantity=Decimal("1"),
        limit_price=Decimal(limit) if limit else None,
        stop_price=Decimal(stop) if stop else None,
    )


def test_limit_buy_fills_at_or_below_limit():
    order = make_order(OrderSide.BUY, OrderType.LIMIT, limit="100")
    assert evaluate(order, Decimal("101")) == (False, None)
    assert evaluate(order, Decimal("100")) == (True, Decimal("100"))
    # market gapped below the limit: fill at the better market price
    assert evaluate(order, Decimal("95")) == (True, Decimal("95"))


def test_limit_sell_fills_at_or_above_limit():
    order = make_order(OrderSide.SELL, OrderType.LIMIT, limit="100")
    assert evaluate(order, Decimal("99")) == (False, None)
    assert evaluate(order, Decimal("105")) == (True, Decimal("105"))


def test_stop_buy_triggers_above():
    order = make_order(OrderSide.BUY, OrderType.STOP, stop="100")
    assert evaluate(order, Decimal("99"))[0] is False
    assert evaluate(order, Decimal("100")) == (True, Decimal("100"))
    assert evaluate(order, Decimal("110")) == (True, Decimal("110"))


def test_stop_sell_triggers_below():
    order = make_order(OrderSide.SELL, OrderType.STOP, stop="100")
    assert evaluate(order, Decimal("101"))[0] is False
    assert evaluate(order, Decimal("95")) == (True, Decimal("95"))


def test_stop_limit_sell_arms_then_respects_limit():
    order = make_order(OrderSide.SELL, OrderType.STOP_LIMIT, limit="98", stop="100")
    # above stop: nothing
    assert evaluate(order, Decimal("105"))[0] is False
    assert not order.stop_triggered
    # crashes straight through the limit: armed but NOT filled below limit
    assert evaluate(order, Decimal("90"))[0] is False
    assert order.stop_triggered is True
    # recovers above the limit: fills
    should, price = evaluate(order, Decimal("99"))
    assert should is True and price == Decimal("99")
