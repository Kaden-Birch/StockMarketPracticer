"""Discord configuration API (roadmap 7.5): everything is set up through
the UI — webhook URL and bot token are stored encrypted and never echoed
back. Also exposes a command preview so the UI (and tests) can exercise the
exact handlers the gateway bot uses."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.currentuser import current_username
from ..integrations import discord as discord_integration
from ..marketdata.service import MarketDataService
from ..security import credentials
from ..security.audit import audit
from .deps import get_db, get_market

router = APIRouter(prefix="/discord", tags=["discord"])


class DiscordConfig(BaseModel):
    webhook_url: str | None = Field(default=None, max_length=400)
    bot_token: str | None = Field(default=None, max_length=200)
    events: list[str] | None = None


@router.get("/config")
def get_config(request: Request, session: Session = Depends(get_db)):
    cfg = request.app.state.settings
    return {
        "webhook_configured": bool(
            credentials.load_key(session, cfg.data_dir,
                                 discord_integration.WEBHOOK_PROVIDER)),
        "bot_token_configured": bool(
            credentials.load_key(session, cfg.data_dir,
                                 discord_integration.BOT_TOKEN_PROVIDER)),
        "gateway_available": discord_integration.gateway_available(),
        "events": discord_integration.enabled_events(session),
        "available_events": discord_integration.DEFAULT_EVENTS,
        "commands": discord_integration.COMMANDS,
    }


@router.put("/config")
def set_config(body: DiscordConfig, request: Request,
               session: Session = Depends(get_db)):
    cfg = request.app.state.settings
    changed = []
    if body.webhook_url is not None:
        if body.webhook_url:
            if not body.webhook_url.startswith("https://"):
                raise HTTPException(status_code=422,
                                    detail="Webhook URL must be https://")
            credentials.store_key(session, cfg.data_dir,
                                  discord_integration.WEBHOOK_PROVIDER,
                                  body.webhook_url)
        else:
            credentials.delete_key(session, discord_integration.WEBHOOK_PROVIDER)
        changed.append("webhook")
    if body.bot_token is not None:
        if body.bot_token:
            credentials.store_key(session, cfg.data_dir,
                                  discord_integration.BOT_TOKEN_PROVIDER,
                                  body.bot_token)
        else:
            credentials.delete_key(session, discord_integration.BOT_TOKEN_PROVIDER)
        changed.append("bot_token")
    if body.events is not None:
        unknown = set(body.events) - set(discord_integration.DEFAULT_EVENTS)
        if unknown:
            raise HTTPException(status_code=422,
                                detail=f"Unknown event types: {sorted(unknown)}")
        discord_integration.set_enabled_events(session, body.events)
        changed.append("events")
    audit(session, current_username(), "discord.config", ", ".join(changed) or "noop")
    session.commit()
    note = ""
    if "bot_token" in changed:
        note = ("Gateway bot (slash commands) starts on next restart"
                if discord_integration.gateway_available()
                else "Install the optional discord.py dependency to enable "
                     "slash commands; webhook notifications work without it.")
    return {"ok": True, "changed": changed, "note": note}


@router.post("/test")
def send_test(request: Request, session: Session = Depends(get_db)):
    cfg = request.app.state.settings
    url = credentials.load_key(session, cfg.data_dir,
                               discord_integration.WEBHOOK_PROVIDER)
    if not url:
        raise HTTPException(status_code=422, detail="No webhook URL configured")
    ok = discord_integration.post_webhook(
        url, "✅ AIPTP Discord integration test — you're connected!")
    if not ok:
        raise HTTPException(status_code=502, detail="Discord did not accept the message")
    return {"ok": True}


class CommandPreview(BaseModel):
    command: str
    arg: str = ""


@router.post("/commands/preview")
def preview_command(
    body: CommandPreview,
    session: Session = Depends(get_db),
    market: MarketDataService = Depends(get_market),
):
    """Run a slash-command handler as the current user — the same code path
    the gateway bot uses, so the UI can demo /portfolio etc."""
    reply = discord_integration.run_command(
        session, market, current_username(), body.command, body.arg)
    return {"command": body.command, "reply": reply}


@router.get("/roles/{username}")
def suggested_roles(username: str, session: Session = Depends(get_db)):
    """Automatic role assignment preview (roadmap 7.5). The gateway bot
    applies these in Discord; without it they're advisory."""
    from sqlalchemy import select

    from ..gamify.levels import level_from_xp
    from ..gamify.service import get_profile, total_xp
    from ..storage.models import CompetitionEntry

    profile = get_profile(session)
    level = level_from_xp(total_xp(profile))
    wins = 0  # competition wins accrue once competitions end; advisory for now
    entries = session.scalars(select(CompetitionEntry).where(
        CompetitionEntry.username == username)).all()
    return {
        "username": username,
        "level": level,
        "competitions_entered": len(entries),
        "roles": discord_integration.role_for_profile(level, wins),
    }
