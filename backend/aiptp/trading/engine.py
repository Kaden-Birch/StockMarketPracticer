"""Execution simulator: order placement, validation, and fills.

M1 fill policy: orders fill against the latest real quote from the MDAL.
Queue-to-next-open for market orders placed outside market hours arrives with
M2 (documented deviation from PRD §9 realism knobs; fills are still real
prices, never fabricated)."""

from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.models import (
    Holding,
    Lot,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Origin,
    Portfolio,
    Transaction,
)
from . import triggers
from .accounting import consume_lots, total_quantity

CASH_PLACES = Decimal("0.01")
QTY_PLACES = Decimal("0.000001")


class TradingError(Exception):
    pass


def _get_or_create_holding(session: Session, portfolio: Portfolio, symbol: str) -> Holding:
    holding = session.scalar(
        select(Holding).where(Holding.portfolio_id == portfolio.id, Holding.symbol == symbol)
    )
    if holding is None:
        holding = Holding(portfolio_id=portfolio.id, symbol=symbol, quantity=Decimal("0"))
        session.add(holding)
        session.flush()
    return holding


def validate_order(
    session: Session,
    portfolio: Portfolio,
    symbol: str,
    side: OrderSide,
    type_: OrderType,
    quantity: Decimal | None,
    notional: Decimal | None,
    limit_price: Decimal | None,
    stop_price: Decimal | None,
) -> None:
    if (quantity is None) == (notional is None):
        raise TradingError("Provide exactly one of quantity or notional")
    if quantity is not None and quantity <= 0:
        raise TradingError("Quantity must be positive")
    if notional is not None:
        if notional <= 0:
            raise TradingError("Notional must be positive")
        if type_ != OrderType.MARKET or side != OrderSide.BUY:
            raise TradingError("Notional sizing is only supported for market buy orders")
    if type_ in (OrderType.LIMIT, OrderType.STOP_LIMIT) and limit_price is None:
        raise TradingError(f"{type_.value} orders require a limit price")
    if type_ in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price is None:
        raise TradingError(f"{type_.value} orders require a stop price")
    if limit_price is not None and limit_price <= 0:
        raise TradingError("Limit price must be positive")
    if stop_price is not None and stop_price <= 0:
        raise TradingError("Stop price must be positive")
    if side == OrderSide.SELL and quantity is not None:
        holding = session.scalar(
            select(Holding).where(Holding.portfolio_id == portfolio.id, Holding.symbol == symbol)
        )
        held = holding.quantity if holding else Decimal("0")
        pending_sells = session.scalars(
            select(Order).where(
                Order.portfolio_id == portfolio.id,
                Order.symbol == symbol,
                Order.side == OrderSide.SELL,
                Order.status == OrderStatus.PENDING,
            )
        ).all()
        committed = sum((o.quantity for o in pending_sells if o.quantity), Decimal("0"))
        if quantity + committed > held:
            raise TradingError(
                f"Insufficient shares: holding {held} {symbol}, "
                f"{committed} already committed to pending sells"
            )


def fill_order(session: Session, order: Order, price: Decimal) -> Transaction:
    """Execute a fill at `price`. Adjusts cash, lots, and holding quantity,
    and appends the immutable transaction. Raises TradingError (marking the
    order REJECTED) if the portfolio can no longer support the fill."""
    portfolio = session.get(Portfolio, order.portfolio_id)
    symbol = order.symbol
    now = datetime.now(timezone.utc)

    if order.side == OrderSide.BUY:
        if order.notional is not None:
            quantity = (order.notional / price).quantize(QTY_PLACES, rounding=ROUND_DOWN)
            if quantity <= 0:
                _reject(order, "Notional too small for one fractional share unit")
                raise TradingError(order.reject_reason)
        else:
            quantity = order.quantity
        cost = (quantity * price).quantize(CASH_PLACES)
        if cost > portfolio.cash_balance:
            _reject(order, f"Insufficient cash: need {cost}, have {portfolio.cash_balance}")
            raise TradingError(order.reject_reason)
        portfolio.cash_balance = (portfolio.cash_balance - cost).quantize(CASH_PLACES)
        holding = _get_or_create_holding(session, portfolio, symbol)
        session.add(Lot(holding_id=holding.id, quantity_remaining=quantity, unit_cost=price, acquired_at=now))
        holding.quantity += quantity
        realized = None
        amount = cost
    else:
        quantity = order.quantity
        holding = session.scalar(
            select(Holding).where(Holding.portfolio_id == portfolio.id, Holding.symbol == symbol)
        )
        if holding is None or holding.quantity < quantity:
            held = holding.quantity if holding else Decimal("0")
            _reject(order, f"Insufficient shares: need {quantity}, have {held}")
            raise TradingError(order.reject_reason)
        realized = consume_lots(holding.lots, quantity, price, portfolio.cost_basis_method)
        realized = realized.quantize(CASH_PLACES)
        holding.quantity = total_quantity(holding.lots)
        proceeds = (quantity * price).quantize(CASH_PLACES)
        portfolio.cash_balance = (portfolio.cash_balance + proceeds).quantize(CASH_PLACES)
        amount = proceeds

    order.status = OrderStatus.FILLED
    order.filled_at = now
    txn = Transaction(
        portfolio_id=portfolio.id,
        order_id=order.id,
        symbol=symbol,
        side=order.side,
        quantity=quantity,
        price=price,
        amount=amount,
        realized_pnl=realized,
        origin=order.origin,
        executed_at=now,
    )
    session.add(txn)
    return txn


def _reject(order: Order, reason: str) -> None:
    order.status = OrderStatus.REJECTED
    order.reject_reason = reason


def place_order(
    session: Session,
    portfolio: Portfolio,
    *,
    symbol: str,
    side: OrderSide,
    type_: OrderType,
    quantity: Decimal | None = None,
    notional: Decimal | None = None,
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    origin: Origin = Origin.MANUAL,
    current_price: Decimal | None = None,
) -> tuple[Order, Transaction | None]:
    """Create an order. Market orders (and marketable limit/stop orders) fill
    immediately when current_price is supplied; everything else goes PENDING
    for the watcher."""
    symbol = symbol.upper()
    validate_order(session, portfolio, symbol, side, type_, quantity, notional, limit_price, stop_price)
    order = Order(
        portfolio_id=portfolio.id,
        symbol=symbol,
        side=side,
        type=type_,
        quantity=quantity,
        notional=notional,
        limit_price=limit_price,
        stop_price=stop_price,
        origin=origin,
    )
    session.add(order)
    session.flush()

    txn = None
    if current_price is not None:
        should_fill, fill_price = triggers.evaluate(order, current_price)
        if should_fill:
            txn = fill_order(session, order, fill_price)
    elif order.type == OrderType.MARKET:
        raise TradingError("Market orders require a current price to fill against")
    return order, txn


def evaluate_pending_orders(
    session: Session, prices: dict[str, Decimal]
) -> list[Transaction]:
    """Run trigger evaluation for all PENDING orders whose symbol has a fresh
    price. Returns transactions for fills. Rejected fills (e.g. cash spent
    since placement) are marked on the order and skipped."""
    pending = session.scalars(
        select(Order)
        .where(Order.status == OrderStatus.PENDING, Order.symbol.in_(list(prices)))
        .order_by(Order.created_at)
    ).all()
    fills: list[Transaction] = []
    for order in pending:
        price = prices[order.symbol]
        should_fill, fill_price = triggers.evaluate(order, price)
        if not should_fill:
            continue
        try:
            fills.append(fill_order(session, order, fill_price))
        except TradingError:
            continue  # order is now REJECTED with a recorded reason
    return fills
