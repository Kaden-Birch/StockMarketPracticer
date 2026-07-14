"""Career mode + mandates API (roadmap 8.3-8.5), mounted by the career
module."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..career import engine as career_engine
from ..career import mandates as mandates_mod
from ..core.currentuser import current_username
from ..marketdata.service import MarketDataService
from ..security.audit import audit
from .deps import get_db, get_market, get_portfolio_or_404

router = APIRouter(prefix="/career", tags=["career"])
mandate_router = APIRouter(prefix="/portfolios/{portfolio_id}/mandate",
                           tags=["career"])


@router.get("")
def get_career(session: Session = Depends(get_db)):
    return career_engine.view(session, current_username())


@router.post("/evaluate")
def evaluate_career(
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    out = career_engine.evaluate(session, market, current_username())
    session.commit()
    return out


@router.get("/mandates")
def list_mandates():
    return [
        {"id": mid, **mandates_mod.MANDATE_INFO[mid]}
        for mid in mandates_mod.MANDATE_IDS
    ]


class MandateSet(BaseModel):
    mandate: str  # "" clears


@mandate_router.get("")
def get_mandate(
    portfolio_id: str,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    return mandates_mod.compliance(session, portfolio, market)


@mandate_router.put("")
def set_mandate(
    portfolio_id: str,
    body: MandateSet,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    if body.mandate and body.mandate not in mandates_mod.MANDATE_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"mandate must be one of {list(mandates_mod.MANDATE_IDS)} or empty")
    portfolio = get_portfolio_or_404(session, portfolio_id)
    portfolio.mandate = body.mandate
    audit(session, current_username(), "mandate.set",
          f"{portfolio.name} -> {body.mandate or 'none'}")
    session.commit()
    return mandates_mod.compliance(session, portfolio, market)
