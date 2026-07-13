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
    """Fetch a portfolio the current user may access: owner, member of the
    (cooperative) portfolio, admin, or any pre-multi-user 'local' portfolio.
    Non-members get a 404, not a 403 — existence is not leaked."""
    from sqlalchemy import select

    from ..core.currentuser import LOCAL_USER, current_username, is_admin
    from ..storage.models import PortfolioMember

    portfolio = session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    user = current_username()
    if (
        portfolio.owner in (user, LOCAL_USER)
        or is_admin()
        or session.scalar(
            select(PortfolioMember.id).where(
                PortfolioMember.portfolio_id == portfolio_id,
                PortfolioMember.username == user,
            )
        )
        is not None
    ):
        return portfolio
    raise HTTPException(status_code=404, detail="Portfolio not found")


def require_admin() -> None:
    """Route dependency: admin-only endpoints (user management, provider
    keys, backups). In desktop mode the local user is implicitly admin."""
    from ..core.currentuser import is_admin

    if not is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")


def require_module(module_id: str):
    """Route dependency: 409 when the module isn't running (disabled by the
    user, a failed start, or a missing dependency)."""

    def dependency(request: Request) -> None:
        manager = getattr(request.app.state, "module_manager", None)
        if manager is not None and not manager.is_running(module_id):
            reason = (manager.disabled_reasons.get(module_id)
                      or ("failed to start" if module_id in manager.errors else "disabled"))
            raise HTTPException(
                status_code=409,
                detail=f"The {module_id} module is not active ({reason})",
            )

    return dependency


def require_preset(module_id: str):
    """Route dependency for portfolio-scoped module endpoints: 409 when the
    portfolio's experience preset disables this module."""

    def dependency(portfolio_id: str, request: Request) -> None:
        from ..core.presets import preset_allows

        session: Session = request.app.state.session_factory()
        try:
            portfolio = session.get(Portfolio, portfolio_id)
            if portfolio is not None and not preset_allows(portfolio.preset, module_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"This portfolio's {portfolio.preset} preset disables {module_id}",
                )
        finally:
            session.close()

    return dependency
