from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..storage.models import RecurringPlan
from .deps import get_db, get_market, get_portfolio_or_404
from .schemas import RecurringPlanCreate, RecurringPlanOut, RecurringPlanUpdate

router = APIRouter(prefix="/portfolios/{portfolio_id}/plans", tags=["recurring"])


@router.post("", response_model=RecurringPlanOut, status_code=201)
def create_plan(
    portfolio_id: str,
    body: RecurringPlanCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    get_portfolio_or_404(session, portfolio_id)
    try:
        market.get_quote(body.symbol)  # validate the symbol up front
    except SymbolNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {body.symbol}")
    except MarketDataError:
        pass  # provider hiccup shouldn't block plan creation
    start = body.start_at or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    plan = RecurringPlan(
        portfolio_id=portfolio_id,
        symbol=body.symbol,
        amount=body.amount,
        cadence=body.cadence,
        next_run_at=start,
    )
    session.add(plan)
    session.commit()
    return plan


@router.get("", response_model=list[RecurringPlanOut])
def list_plans(portfolio_id: str, session: Session = Depends(get_db)):
    get_portfolio_or_404(session, portfolio_id)
    return session.scalars(
        select(RecurringPlan)
        .where(RecurringPlan.portfolio_id == portfolio_id)
        .order_by(RecurringPlan.created_at)
    ).all()


@router.patch("/{plan_id}", response_model=RecurringPlanOut)
def update_plan(
    portfolio_id: str,
    plan_id: str,
    body: RecurringPlanUpdate,
    session: Session = Depends(get_db),
):
    get_portfolio_or_404(session, portfolio_id)
    plan = session.get(RecurringPlan, plan_id)
    if plan is None or plan.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Plan not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(plan, field, value)
    session.commit()
    return plan


@router.delete("/{plan_id}", status_code=204)
def delete_plan(portfolio_id: str, plan_id: str, session: Session = Depends(get_db)):
    get_portfolio_or_404(session, portfolio_id)
    plan = session.get(RecurringPlan, plan_id)
    if plan is None or plan.portfolio_id != portfolio_id:
        raise HTTPException(status_code=404, detail="Plan not found")
    session.delete(plan)
    session.commit()
