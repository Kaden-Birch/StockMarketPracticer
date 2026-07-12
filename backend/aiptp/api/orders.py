from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.events import EventBus
from ..marketdata.base import MarketDataError, Quote, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..storage.models import (
    Holding,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PercentOf,
    Portfolio,
    Transaction,
)
from ..trading.engine import TradingError, place_order
from ..trading.rebalance import execute_rebalance, plan_rebalance
from .deps import get_bus, get_db, get_market, get_portfolio_or_404
from .schemas import BatchOrderCreate, OrderCreate, OrderOut, RebalanceRequest

router = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["orders"])


def _publish_fill(bus: EventBus, portfolio_id: str, order: Order, txn: Transaction) -> None:
    bus.publish(
        "order_filled",
        {
            "portfolio_id": portfolio_id,
            "order_id": order.id,
            "symbol": txn.symbol,
            "side": txn.side.value,
            "quantity": str(txn.quantity),
            "price": str(txn.price),
            "origin": txn.origin.value,
        },
    )


def _resolve_percent(
    session: Session,
    portfolio: Portfolio,
    body: OrderCreate,
    quote: Quote | None,
    fx: Decimal,
    market: MarketDataService,
) -> tuple[Decimal | None, Decimal | None]:
    """Convert percent sizing into quantity/notional at placement time."""
    if body.percent is None:
        return body.quantity, body.notional
    if body.quantity is not None or body.notional is not None:
        raise TradingError("Percent sizing cannot be combined with quantity or notional")
    if body.percent_of is None:
        raise TradingError("percent_of is required with percent sizing")
    if body.percent_of == PercentOf.POSITION:
        if body.side != OrderSide.SELL:
            raise TradingError("Percent-of-position sizing is for sell orders")
        holding = session.scalar(
            select(Holding).where(
                Holding.portfolio_id == portfolio.id, Holding.symbol == body.symbol
            )
        )
        held = holding.quantity if holding else Decimal("0")
        qty = (held * body.percent / 100).quantize(Decimal("0.000001"))
        if qty <= 0:
            raise TradingError(f"No {body.symbol} position to sell a percentage of")
        return qty, None
    if body.side != OrderSide.BUY or body.type != OrderType.MARKET:
        raise TradingError("Percent-of-cash/portfolio sizing is for market buy orders")
    if body.percent_of == PercentOf.CASH:
        base = portfolio.cash_balance
    else:  # PORTFOLIO
        from ..portfolio.service import value_portfolio

        base = Decimal(value_portfolio(portfolio, market)["total_value"])
    notional = (base * body.percent / 100).quantize(Decimal("0.01"))
    if notional <= 0:
        raise TradingError("Percent sizing resolved to zero")
    return None, notional


def _place_one(
    session: Session,
    portfolio: Portfolio,
    body: OrderCreate,
    market: MarketDataService,
) -> tuple[Order, Transaction | None]:
    try:
        quote = market.get_quote(body.symbol)
    except SymbolNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {body.symbol}")
    except MarketDataError as exc:
        if body.type == OrderType.MARKET:
            raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}")
        quote = None  # pending order types can wait for the watcher

    fx = Decimal("1")
    if quote is not None and quote.currency != portfolio.currency:
        try:
            fx = market.get_fx_rate(quote.currency, portfolio.currency)
        except MarketDataError as exc:
            raise HTTPException(status_code=503, detail=f"FX rate unavailable: {exc}")

    quantity, notional = _resolve_percent(session, portfolio, body, quote, fx, market)
    return place_order(
        session,
        portfolio,
        symbol=body.symbol,
        side=body.side,
        type_=body.type,
        quantity=quantity,
        notional=notional,
        limit_price=body.limit_price,
        stop_price=body.stop_price,
        trail_amount=body.trail_amount,
        trail_percent=body.trail_percent,
        percent=body.percent,
        percent_of=body.percent_of,
        current_price=quote.price if quote else None,
        fx_rate=fx,
        quote_currency=quote.currency if quote else None,
    )


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(
    portfolio_id: str,
    body: OrderCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
    bus: EventBus = Depends(get_bus),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        order, txn = _place_one(session, portfolio, body, market)
        session.commit()
    except TradingError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    if txn is not None:
        _publish_fill(bus, portfolio.id, order, txn)
    return order


@router.post("/orders/batch", status_code=201)
def create_orders_batch(
    portfolio_id: str,
    body: BatchOrderCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
    bus: EventBus = Depends(get_bus),
):
    """Mass buy/sell: each order is attempted independently; failures don't
    roll back earlier fills."""
    portfolio = get_portfolio_or_404(session, portfolio_id)
    results = []
    for item in body.orders:
        try:
            order, txn = _place_one(session, portfolio, item, market)
            session.commit()
            results.append({"symbol": item.symbol, "status": order.status.value,
                            "order_id": order.id})
            if txn is not None:
                _publish_fill(bus, portfolio.id, order, txn)
        except (TradingError, HTTPException) as exc:
            session.rollback()
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            results.append({"symbol": item.symbol, "status": "ERROR", "error": detail})
    return {"results": results}


@router.post("/rebalance")
def rebalance(
    portfolio_id: str,
    body: RebalanceRequest,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
    bus: EventBus = Depends(get_bus),
):
    """Preview (execute=false) or execute (execute=true) a rebalance to the
    given target weights."""
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        plan = plan_rebalance(portfolio, body.targets, market)
    except TradingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not body.execute:
        return {"plan": plan, "executed": None}
    results = execute_rebalance(session, portfolio, plan, market)
    session.commit()
    bus.publish("rebalanced", {"portfolio_id": portfolio.id, "results": results})
    return {"plan": plan, "executed": results}


@router.get("/orders", response_model=list[OrderOut])
def list_orders(
    portfolio_id: str,
    status: OrderStatus | None = None,
    session: Session = Depends(get_db),
):
    get_portfolio_or_404(session, portfolio_id)
    query = (
        select(Order).where(Order.portfolio_id == portfolio_id).order_by(Order.created_at.desc())
    )
    if status:
        query = query.where(Order.status == status)
    return session.scalars(query).all()


@router.delete("/orders/{order_id}", response_model=OrderOut)
def cancel_order(portfolio_id: str, order_id: str, session: Session = Depends(get_db)):
    get_portfolio_or_404(session, portfolio_id)
    order = session.get(Order, order_id)
    if order is None or order.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}, not PENDING")
    order.status = OrderStatus.CANCELLED
    session.commit()
    return order
