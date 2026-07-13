"""Read-only sharing (roadmap 7.6): revocable random-token links that expose
a portfolio performance snapshot or a strategy definition without requiring
an account. The public /shared/{token} endpoint is auth-exempt and never
reveals who owns the underlying portfolio (anonymous by default)."""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.currentuser import current_username, is_admin
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..security.audit import audit
from ..storage.models import Portfolio, ShareLink, Strategy
from .deps import get_db, get_market, get_portfolio_or_404

router = APIRouter(prefix="/shares", tags=["sharing"])
public_router = APIRouter(prefix="/shared", tags=["sharing"])


def _new_token() -> str:
    return secrets.token_urlsafe(24)  # 32 chars, fits String(48)


def _create_link(session: Session, kind: str, target_id: str) -> dict:
    link = ShareLink(
        token=_new_token(), kind=kind, target_id=target_id,
        created_by=current_username(),
    )
    session.add(link)
    audit(session, current_username(), "share.created", f"{kind} {target_id}")
    session.commit()
    return {"token": link.token, "kind": link.kind, "target_id": link.target_id,
            "url": f"/shared/{link.token}"}


@router.post("/portfolios/{portfolio_id}", status_code=201)
def share_portfolio(portfolio_id: str, session: Session = Depends(get_db)):
    get_portfolio_or_404(session, portfolio_id)  # must be able to access it
    return _create_link(session, "portfolio", portfolio_id)


@router.post("/strategies/{strategy_id}", status_code=201)
def share_strategy(strategy_id: str, session: Session = Depends(get_db)):
    if session.get(Strategy, strategy_id) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return _create_link(session, "strategy", strategy_id)


@router.get("")
def list_my_shares(session: Session = Depends(get_db)):
    query = select(ShareLink).order_by(ShareLink.created_at.desc())
    if not is_admin():
        query = query.where(ShareLink.created_by == current_username())
    return [
        {"token": s.token, "kind": s.kind, "target_id": s.target_id,
         "revoked": s.revoked, "created_at": s.created_at.isoformat()}
        for s in session.scalars(query)
    ]


@router.delete("/{token}", status_code=204)
def revoke_share(token: str, session: Session = Depends(get_db)):
    link = session.get(ShareLink, token)
    if link is None or (link.created_by != current_username() and not is_admin()):
        raise HTTPException(status_code=404, detail="Share link not found")
    link.revoked = True
    audit(session, current_username(), "share.revoked", f"{link.kind} {link.target_id}")
    session.commit()


# ---- Public (auth-exempt) ----

def _live_link(session: Session, token: str) -> ShareLink:
    link = session.get(ShareLink, token)
    if link is None or link.revoked:
        raise HTTPException(status_code=404, detail="Share link not found")
    return link


@public_router.get("/{token}")
def view_shared(token: str, request: Request, session: Session = Depends(get_db),
                market: MarketDataService = Depends(get_market)):
    link = _live_link(session, token)
    if link.kind == "portfolio":
        portfolio = session.get(Portfolio, link.target_id)
        if portfolio is None:
            raise HTTPException(status_code=404, detail="Share link not found")
        view = value_portfolio(portfolio, market)
        # Anonymous, read-only performance view: strip identity and internals.
        from decimal import Decimal

        starting = Decimal(view["starting_balance"])
        ret_pct = (
            str((Decimal(view["lifetime_return"]) / starting * 100).quantize(Decimal("0.01")))
            if starting else None
        )
        return {
            "kind": "portfolio",
            "name": view["name"],
            "currency": view["currency"],
            "mode": view["mode"],
            "created_at": view["created_at"],
            "starting_balance": view["starting_balance"],
            "total_value": view["total_value"],
            "lifetime_return": view["lifetime_return"],
            "total_return_pct": ret_pct,
            "day_change": view["day_change"],
            "holdings": [
                {"symbol": h["symbol"], "quantity": h["quantity"],
                 "market_value": h["market_value"]}
                for h in view["holdings"]
            ],
        }
    strategy = session.get(Strategy, link.target_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return {
        "kind": "strategy",
        "name": strategy.name,
        "description": strategy.description,
        "universe": json.loads(strategy.universe),
        "entry_trigger": json.loads(strategy.entry_trigger),
        "exit_trigger": json.loads(strategy.exit_trigger) if strategy.exit_trigger else None,
        "entry_notional": str(strategy.entry_notional),
        "benchmark": strategy.benchmark,
    }


@router.post("/{token}/import", status_code=201)
def import_shared_strategy(token: str, session: Session = Depends(get_db)):
    """Copy a shared strategy into this deployment (roadmap 7.6: strategy
    sharing with import). Requires login; the copy is a fresh, editable row."""
    link = _live_link(session, token)
    if link.kind != "strategy":
        raise HTTPException(status_code=422, detail="Only strategy links can be imported")
    source = session.get(Strategy, link.target_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    copy = Strategy(
        name=f"{source.name} (imported)",
        description=source.description,
        universe=source.universe,
        entry_trigger=source.entry_trigger,
        exit_trigger=source.exit_trigger,
        entry_notional=source.entry_notional,
        initial_cash=source.initial_cash,
        benchmark=source.benchmark,
    )
    session.add(copy)
    audit(session, current_username(), "share.imported", f"strategy {source.id}")
    session.commit()
    return {"id": copy.id, "name": copy.name}
