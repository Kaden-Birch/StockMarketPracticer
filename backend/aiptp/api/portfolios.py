from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..storage.models import Portfolio, Transaction
from .deps import get_db, get_market, get_portfolio_or_404
from .schemas import PortfolioCreate, PortfolioUpdate, TransactionOut

router = APIRouter(prefix="/portfolios", tags=["portfolios"])
symbols_router = APIRouter(prefix="/symbols", tags=["portfolios"])


@symbols_router.get("/{symbol}/transactions", response_model=list[TransactionOut])
def symbol_transactions(symbol: str, session: Session = Depends(get_db)):
    """All transactions for a symbol across portfolios — feeds the company
    chart's buy/sell/dividend/split overlay markers."""
    return session.scalars(
        select(Transaction)
        .where(Transaction.symbol == symbol.upper())
        .order_by(Transaction.executed_at)
    ).all()


@router.post("", status_code=201)
def create_portfolio(
    body: PortfolioCreate,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    from ..core.currentuser import current_username

    portfolio = Portfolio(
        owner=current_username(),
        name=body.name,
        description=body.description,
        currency=body.currency,
        starting_balance=body.starting_balance,
        cash_balance=body.starting_balance,
        cost_basis_method=body.cost_basis_method,
        mode=body.mode,
        preset=body.preset,
        ends_at=body.ends_at,
        game_id=body.game_id,
        notes=body.notes,
    )
    session.add(portfolio)
    session.commit()
    return value_portfolio(portfolio, market)


@router.get("")
def list_portfolios(
    game: str = "",
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    from ..core.currentuser import LOCAL_USER, current_username, is_admin
    from ..storage.models import PortfolioMember

    user = current_username()
    # Scenario replay portfolios live on the Scenarios page (historical
    # prices) and AI-opponent portfolios on their competition pages — both
    # stay out of the personal dashboard.
    query = (select(Portfolio)
             .where(Portfolio.scenario_session_id.is_(None),
                    ~Portfolio.owner.startswith("ai:"))
             .order_by(Portfolio.created_at))
    if game:
        query = query.where(Portfolio.game_id == (None if game == "none" else game))
    if not is_admin():
        member_ids = select(PortfolioMember.portfolio_id).where(
            PortfolioMember.username == user
        )
        query = query.where(
            (Portfolio.owner.in_([user, LOCAL_USER])) | (Portfolio.id.in_(member_ids))
        )
    portfolios = session.scalars(query).all()
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
