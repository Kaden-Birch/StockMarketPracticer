"""Persistent-mentor API (roadmap 8.1), mounted by the ai_mentor module."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.currentuser import current_username
from ..marketdata.service import MarketDataService
from ..mentor import engine as mentor_engine
from ..storage.models import MentorObservation, ObservationStatus
from .deps import get_db, get_market

router = APIRouter(prefix="/mentor", tags=["mentor"])


@router.get("")
def get_mentor(session: Session = Depends(get_db)):
    return mentor_engine.view_mentor(session, current_username())


@router.post("/refresh")
def refresh_mentor(
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    view = mentor_engine.analyze(session, market, current_username())
    session.commit()
    return view


@router.post("/observations/{observation_id}/acknowledge")
def acknowledge(observation_id: str, session: Session = Depends(get_db)):
    row = session.get(MentorObservation, observation_id)
    if row is None or row.username != current_username():
        raise HTTPException(status_code=404, detail="Observation not found")
    row.status = ObservationStatus.ACKNOWLEDGED
    session.commit()
    return {"ok": True}


@router.post("/narrative")
def mentor_narrative(request: Request, session: Session = Depends(get_db)):
    """LLM-written mentor note over the deterministic findings. 409 when no
    model is loaded — the grounded observations above never need one."""
    manager = request.app.state.model_manager
    if not manager.runtime.model_id:
        raise HTTPException(
            status_code=409,
            detail="No AI model loaded — load one in AI Models to get narrated notes",
        )
    view = mentor_engine.view_mentor(session, current_username())
    if not view["observations"] and not view["profile"]["style"]:
        raise HTTPException(status_code=409, detail="Run a mentor refresh first")
    return {"narrative": mentor_engine.narrative(manager.runtime, view)}
