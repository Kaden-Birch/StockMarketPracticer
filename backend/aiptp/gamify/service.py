"""XP awarding with anti-abuse caps, level-up notifications, and the
gamification opt-out (PRD §23: rewards never track trading frequency)."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.presets import preset_allows
from ..storage.models import AppSetting, Portfolio, Profile, XpEvent
from .levels import level_from_xp, title_for_level

log = logging.getLogger(__name__)

GAMIFICATION_KEY = "gamification.enabled"

CATEGORIES = ("education", "research", "portfolio", "challenge")

# XP per action kind and per-day caps for repeatable UI-driven actions.
ACTION_XP: dict[str, tuple[str, int, int | None]] = {
    # kind: (category, xp, daily_cap_events)
    "company_viewed": ("research", 5, 5),
    "companies_compared": ("research", 10, 3),
    "analytics_reviewed": ("portfolio", 10, 2),
    "backtest_completed": ("research", 20, 3),
    "coach_suggestion_read": ("education", 15, 4),
    # M10 learning system — education XP, daily-capped like everything else
    "concept_viewed": ("education", 5, 8),
    "quiz_passed": ("education", 15, 5),
    "path_completed": ("education", 50, 1),
}


def gamification_enabled(session: Session) -> bool:
    setting = session.get(AppSetting, GAMIFICATION_KEY)
    return setting is None or setting.value != "off"


def set_gamification(session: Session, enabled: bool) -> None:
    setting = session.get(AppSetting, GAMIFICATION_KEY)
    if setting is None:
        setting = AppSetting(key=GAMIFICATION_KEY)
        session.add(setting)
    setting.value = "on" if enabled else "off"


def get_profile(session: Session) -> Profile:
    profile = session.scalar(select(Profile).limit(1))
    if profile is None:
        profile = Profile()
        session.add(profile)
        session.flush()
    return profile


def total_xp(profile: Profile) -> int:
    return (profile.education_xp + profile.research_xp
            + profile.portfolio_xp + profile.challenge_xp)


def _events_today(session: Session, kind: str) -> int:
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.scalar(
            select(func.count(XpEvent.id)).where(
                XpEvent.kind == kind, XpEvent.created_at >= day_start
            )
        )
        or 0
    )


def award(
    session: Session,
    bus,
    category: str,
    kind: str,
    amount: int,
    reason: str = "",
    portfolio_id: str | None = None,
) -> bool:
    """Grant XP. Returns False when gamification is off or a daily cap for
    this kind is exhausted."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown XP category: {category}")
    if amount <= 0 or not gamification_enabled(session):
        return False
    if portfolio_id:
        # Experience preset gating (roadmap 6.11.5): Learning/Professional
        # portfolios earn no XP.
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is not None and not preset_allows(portfolio.preset, "gamification"):
            return False
    cap = ACTION_XP.get(kind, (None, None, None))[2]
    if cap is not None and _events_today(session, kind) >= cap:
        return False

    profile = get_profile(session)
    before_level = level_from_xp(total_xp(profile))
    setattr(profile, f"{category}_xp", getattr(profile, f"{category}_xp") + amount)
    session.add(XpEvent(category=category, kind=kind, amount=amount,
                        reason=reason[:200], portfolio_id=portfolio_id))
    if portfolio_id:
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is not None:
            portfolio.game_xp += amount

    after_level = level_from_xp(total_xp(profile))
    if after_level > before_level and bus is not None:
        bus.publish(
            "level_up",
            {"level": after_level, "title": title_for_level(after_level)},
            session=session,
        )
    return True


def award_action(session: Session, bus, kind: str,
                 reason: str = "", portfolio_id: str | None = None) -> bool:
    """Award a predefined UI-driven action (capped per day)."""
    spec = ACTION_XP.get(kind)
    if spec is None:
        raise ValueError(f"Unknown action kind: {kind}")
    category, amount, _ = spec
    return award(session, bus, category, kind, amount, reason, portfolio_id)
