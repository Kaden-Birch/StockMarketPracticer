"""Future game mode API (M11 note 11), mounted by the future module. Every
response carries simulated=true and the disclaimer."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.currentuser import current_username, is_admin
from ..future import engine
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..security.audit import audit
from ..storage.models import FutureSession, OrderSide, Portfolio
from ..trading.engine import TradingError
from .deps import get_db, get_market

router = APIRouter(prefix="/future", tags=["future"])


class FutureCreate(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=engine.MAX_SYMBOLS)
    starting_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    seed: str = Field(default="", max_length=32)


class FutureTrade(BaseModel):
    symbol: str
    side: OrderSide
    quantity: Decimal | None = Field(default=None, gt=0)
    notional: Decimal | None = Field(default=None, gt=0)


class FutureAdvance(BaseModel):
    days: int = Field(default=5, ge=1, le=260)


def _get_or_404(db: Session, session_id: str) -> FutureSession:
    sess = db.get(FutureSession, session_id)
    if sess is None or (sess.username != current_username() and not is_admin()):
        raise HTTPException(status_code=404, detail="Future session not found")
    return sess


@router.get("")
def list_sessions(db: Session = Depends(get_db)):
    return {
        "disclaimer": engine.DISCLAIMER,
        "sessions": [
            {"id": s.id, "symbols": s.symbols, "step": s.current_step,
             "virtual_date": engine.virtual_date(s),
             "created_at": s.created_at.isoformat()}
            for s in engine.list_sessions(db, current_username())
        ],
    }


@router.post("/sessions", status_code=201)
def start(body: FutureCreate, db: Session = Depends(get_db),
          market: MarketDataService = Depends(get_market)):
    try:
        sess = engine.create_session(db, market, current_username(),
                                     body.symbols, body.starting_cash,
                                     body.seed or None)
    except engine.FutureError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503,
                            detail=f"Calibration data unavailable: {exc}")
    audit(db, current_username(), "future.started",
          ",".join(body.symbols)[:180])
    db.commit()
    return engine.session_view(db, sess)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    return engine.session_view(db, _get_or_404(db, session_id))


@router.post("/sessions/{session_id}/trade", status_code=201)
def future_trade(session_id: str, body: FutureTrade,
                 db: Session = Depends(get_db)):
    sess = _get_or_404(db, session_id)
    if (body.quantity is None) == (body.notional is None):
        raise HTTPException(status_code=422,
                            detail="Provide exactly one of quantity or notional")
    try:
        order, txn = engine.trade(db, sess, body.symbol, body.side,
                                  body.quantity, body.notional)
        db.commit()
    except (engine.FutureError, TradingError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return {"order_id": order.id, "status": order.status.value,
            "filled_price": str(txn.price) if txn else None,
            "simulated": True}


@router.post("/sessions/{session_id}/advance")
def future_advance(session_id: str, body: FutureAdvance,
                   db: Session = Depends(get_db)):
    sess = _get_or_404(db, session_id)
    engine.advance(db, sess, body.days)
    db.commit()
    return engine.session_view(db, sess)


@router.delete("/sessions/{session_id}", status_code=204)
def abandon(session_id: str, db: Session = Depends(get_db)):
    sess = _get_or_404(db, session_id)
    portfolio = db.get(Portfolio, sess.portfolio_id)
    if portfolio is not None:
        db.delete(portfolio)
    db.delete(sess)
    audit(db, current_username(), "future.abandoned", sess.id)
    db.commit()
