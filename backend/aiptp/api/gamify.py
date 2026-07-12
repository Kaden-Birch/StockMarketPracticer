from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..gamify import challenges as challenge_service
from ..gamify.achievements import CATALOG, evaluate_achievements
from ..gamify.coach import coach_observations
from ..gamify.levels import level_from_xp, level_progress
from ..gamify.report_card import report_card
from ..gamify.service import (
    ACTION_XP,
    award_action,
    gamification_enabled,
    get_profile,
    set_gamification,
    total_xp,
)
from ..marketdata.base import MarketDataError
from ..storage.models import EarnedAchievement, XpEvent
from .deps import get_bus, get_db, get_market, get_portfolio_or_404

router = APIRouter(prefix="/gamify", tags=["gamification"])
prouter = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["gamification"])


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=80)
    avatar: str | None = Field(default=None, min_length=1, max_length=16)
    gamification_enabled: bool | None = None


class ActionBody(BaseModel):
    kind: str
    reason: str = ""
    portfolio_id: str | None = None


@router.get("/profile")
def profile_view(session: Session = Depends(get_db)):
    profile = get_profile(session)
    session.commit()
    earned = {
        e.achievement_id: e.earned_at.isoformat()
        for e in session.scalars(select(EarnedAchievement)).all()
    }
    recent_xp = session.scalars(
        select(XpEvent).order_by(XpEvent.created_at.desc()).limit(20)
    ).all()
    return {
        "username": profile.username,
        "avatar": profile.avatar,
        "gamification_enabled": gamification_enabled(session),
        "progress": level_progress(total_xp(profile)),
        "xp_by_category": {
            "education": profile.education_xp,
            "research": profile.research_xp,
            "portfolio": profile.portfolio_xp,
            "challenge": profile.challenge_xp,
        },
        "achievements": [
            {
                "id": a.id, "name": a.name, "category": a.category,
                "description": a.description, "xp": a.xp,
                "earned_at": earned.get(a.id),
            }
            for a in CATALOG
        ],
        "recent_xp": [
            {"category": e.category, "kind": e.kind, "amount": e.amount,
             "reason": e.reason, "created_at": e.created_at.isoformat()}
            for e in recent_xp
        ],
    }


@router.patch("/profile")
def update_profile(body: ProfileUpdate, session: Session = Depends(get_db)):
    profile = get_profile(session)
    if body.username is not None:
        profile.username = body.username
    if body.avatar is not None:
        profile.avatar = body.avatar
    if body.gamification_enabled is not None:
        set_gamification(session, body.gamification_enabled)
    session.commit()
    return {"ok": True}


@router.get("/challenges")
def challenges(session: Session = Depends(get_db)):
    out = challenge_service.assignments_view(session)
    session.commit()
    return out


@router.post("/events")
def record_action(
    body: ActionBody,
    session: Session = Depends(get_db),
    bus=Depends(get_bus),
):
    """UI-driven XP events (company viewed, comparison used, coach suggestion
    read, ...). Capped per day server-side."""
    if body.kind not in ACTION_XP:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(ACTION_XP)}")
    awarded = award_action(session, bus, body.kind, body.reason, body.portfolio_id)
    session.commit()
    return {"awarded": awarded}


@router.post("/evaluate")
def evaluate_now(
    session: Session = Depends(get_db),
    market=Depends(get_market),
    bus=Depends(get_bus),
):
    """Run achievement + challenge evaluation on demand (also runs on a
    scheduler cycle)."""
    achievements = evaluate_achievements(session, market, bus)
    completed = challenge_service.evaluate_challenges(session, market, bus)
    session.commit()
    return {"achievements_granted": achievements, "challenges_completed": completed}


@prouter.get("/report-card")
def portfolio_report_card(
    portfolio_id: str,
    session: Session = Depends(get_db),
    market=Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        return report_card(session, portfolio, market)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@prouter.get("/coach")
def portfolio_coach(
    portfolio_id: str,
    session: Session = Depends(get_db),
    market=Depends(get_market),
):
    portfolio = get_portfolio_or_404(session, portfolio_id)
    try:
        return {"observations": coach_observations(session, portfolio, market)}
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@prouter.get("/game")
def game_view(portfolio_id: str, session: Session = Depends(get_db)):
    """Per-game progression (roadmap 6.5)."""
    portfolio = get_portfolio_or_404(session, portfolio_id)
    return {
        "portfolio_id": portfolio.id,
        "mode": portfolio.mode.value,
        "game_xp": portfolio.game_xp,
        "game_level": level_from_xp(portfolio.game_xp),
        "ends_at": portfolio.ends_at.isoformat() if portfolio.ends_at else None,
    }


def run_gamify_cycle(session_factory, market, bus) -> None:
    """Scheduler job: evaluate achievements and challenges periodically."""
    with session_factory() as session:
        if not gamification_enabled(session):
            return
        try:
            evaluate_achievements(session, market, bus)
            challenge_service.evaluate_challenges(session, market, bus)
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            import logging

            logging.getLogger(__name__).exception("Gamify cycle failed")
