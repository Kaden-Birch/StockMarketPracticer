from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import Portfolio, Transaction
from .deps import get_db, get_market, get_portfolio_or_404
from .schemas import PortfolioCreate, PortfolioUpdate, TransactionOut

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.post("", status_code=201)
def create_portfolio(
    body: PortfolioCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = Portfolio(
        name=body.name,
        description=body.description,
        currency=body.currency,
        starting_balance=body.starting_balance,
        cash_balance=body.starting_balance,
        cost_basis_method=body.cost_basis_method,
        notes=body.notes,
    )
    session.add(portfolio)
    session.commit()
    return value_portfolio(portfolio, market)


@router.get("")
def list_portfolios(
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolios = session.scalars(select(Portfolio).order_by(Portfolio.created_at)).all()
    return [value_portfolio(p, market) for p in portfolios]


@router.get("/{portfolio_id}")
def get_portfolio(
    portfolio_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    return value_portfolio(portfolio, market)


@router.patch("/{portfolio_id}")
def update_portfolio(
    portfolio_id: str,
    body: PortfolioUpdate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(portfolio, field, value)
    session.commit()
    return value_portfolio(portfolio, market)


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(portfolio_id: str, session: Session = Depends(get_db)):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    session.delete(portfolio)
    session.commit()


@router.get("/{portfolio_id}/transactions", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: str,
    symbol: str | None = None,
    limit: int = 200,
    session: Session = Depends(get_db),
):
    get_portfolio_or_404(session, portfolio_id)
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    query = (
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.executed_at.desc())
        .limit(limit)
    )
    if symbol:
        query = query.where(Transaction.symbol == symbol.upper())
    return session.scalars(query).all()
