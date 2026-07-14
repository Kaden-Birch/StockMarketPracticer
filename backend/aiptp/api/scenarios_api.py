"""Historical scenario API (roadmap 8.2), mounted by the scenarios module."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.currentuser import current_username, is_admin
from ..marketdata.base import MarketDataError
from ..marketdata.service import MarketDataService
from ..scenario import engine
from ..scenario.catalog import catalog_view
from ..security.audit import audit
from ..storage.models import OrderSide, Portfolio, ScenarioSession
from ..trading.engine import TradingError
from .deps import get_db, get_market

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class SessionCreate(BaseModel):
    scenario_id: str
    display_name: str = Field(default="", max_length=80)


class ScenarioTrade(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: OrderSide
    quantity: Decimal | None = Field(default=None, gt=0)
    notional: Decimal | None = Field(default=None, gt=0)


class Advance(BaseModel):
    days: int = Field(default=1, ge=1, le=260)


def _get_session_or_404(db: Session, session_id: str) -> ScenarioSession:
    sess = db.get(ScenarioSession, session_id)
    if sess is None or (sess.username != current_username() and not is_admin()):
        raise HTTPException(status_code=404, detail="Scenario session not found")
    return sess


@router.get("")
def list_scenarios(db: Session = Depends(get_db)):
    mine = db.scalars(select(ScenarioSession).where(
        ScenarioSession.username == current_username()
    ).order_by(ScenarioSession.created_at.desc())).all()
    return {
        "catalog": catalog_view(),
        "sessions": [
            {"id": s.id, "scenario_id": s.scenario_id, "completed": s.completed,
             "created_at": s.created_at.isoformat()}
            for s in mine
        ],
    }


@router.post("/sessions", status_code=201)
def start_session(
    body: SessionCreate,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    try:
        sess = engine.create_session(db, market, body.scenario_id,
                                     current_username(), body.display_name)
    except engine.ScenarioError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")
    audit(db, current_username(), "scenario.started", body.scenario_id)
    db.commit()
    return engine.session_view(db, market, sess)


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    sess = _get_session_or_404(db, session_id)
    try:
        return engine.session_view(db, market, sess)
    except MarketDataError as exc:
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")


@router.post("/sessions/{session_id}/trade", status_code=201)
def scenario_trade(
    session_id: str,
    body: ScenarioTrade,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    sess = _get_session_or_404(db, session_id)
    if (body.quantity is None) == (body.notional is None):
        raise HTTPException(status_code=422,
                            detail="Provide exactly one of quantity or notional")
    try:
        order, txn = engine.trade(db, market, sess, body.symbol, body.side,
                                  body.quantity, body.notional)
        db.commit()
    except engine.ScenarioError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except TradingError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except MarketDataError as exc:
        db.rollback()
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")
    return {"order_id": order.id, "status": order.status.value,
            "filled_price": str(txn.price) if txn else None}


@router.post("/sessions/{session_id}/advance")
def advance_session(
    session_id: str,
    body: Advance,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    sess = _get_session_or_404(db, session_id)
    try:
        view = engine.advance(db, market, sess, body.days)
        db.commit()
        return view
    except engine.ScenarioError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except MarketDataError as exc:
        db.rollback()
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")


@router.get("/sessions/{session_id}/comparison")
def session_comparison(
    session_id: str,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    sess = _get_session_or_404(db, session_id)
    try:
        return engine.comparison(db, market, sess)
    except MarketDataError as exc:
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")


@router.get("/sessions/{session_id}/history/{symbol}")
def session_history(
    session_id: str,
    symbol: str,
    db: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    sess = _get_session_or_404(db, session_id)
    try:
        return engine.history_upto(market, sess, symbol)
    except engine.ScenarioError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MarketDataError as exc:
        raise HTTPException(status_code=503,
                            detail=f"Historical data unavailable: {exc}")


@router.delete("/sessions/{session_id}", status_code=204)
def abandon_session(session_id: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(db, session_id)
    portfolio = db.get(Portfolio, sess.portfolio_id)
    if portfolio is not None:
        db.delete(portfolio)
    db.delete(sess)
    audit(db, current_username(), "scenario.abandoned", sess.scenario_id)
    db.commit()
