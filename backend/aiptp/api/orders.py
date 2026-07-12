from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.events import EventBus
from ..marketdata.base import MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..storage.models import Order, OrderStatus, OrderType
from ..trading.engine import TradingError, place_order
from .deps import get_bus, get_db, get_market, get_portfolio_or_404
from .schemas import OrderCreate, OrderOut

router = APIRouter(prefix="/portfolios/{portfolio_id}/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    portfolio_id: str,
    body: OrderCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
    bus: EventBus = Depends(get_bus),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        quote = market.get_quote(body.symbol)
    except SymbolNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {body.symbol}")
    except MarketDataError as exc:
        if body.type == OrderType.MARKET:
            raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}")
        quote = None  # pending order types can wait for the watcher

    try:
        order, txn = place_order(
            session,
            portfolio,
            symbol=body.symbol,
            side=body.side,
            type_=body.type,
            quantity=body.quantity,
            notional=body.notional,
            limit_price=body.limit_price,
            stop_price=body.stop_price,
            current_price=quote.price if quote else None,
        )
        session.commit()
    except TradingError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    if txn is not None:
        bus.publish(
            "order_filled",
            {
                "portfolio_id": portfolio.id,
                "order_id": order.id,
                "symbol": txn.symbol,
                "side": txn.side.value,
                "quantity": str(txn.quantity),
                "price": str(txn.price),
                "origin": txn.origin.value,
            },
        )
    return order


@router.get("", response_model=list[OrderOut])
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


@router.delete("/{order_id}", response_model=OrderOut)
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
