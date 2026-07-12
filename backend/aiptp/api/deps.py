from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ..core.events import EventBus
from ..marketdata.service import MarketDataService
from ..storage.models import Portfolio


def get_db(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_market(request: Request) -> MarketDataService:
    return request.app.state.market


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus


def get_portfolio_or_404(session: Session, portfolio_id: str) -> Portfolio:
    portfolio = session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio
