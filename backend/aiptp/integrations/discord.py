"""Discord integration (roadmap 7.5). Configured entirely through the app
UI — the webhook URL and bot token are stored encrypted, never in config
files or the command line.

Two tiers:
  * Webhook notifications — always available once a webhook URL is saved.
    Platform events (trades, achievements, AI analyses, ...) become Discord
    messages.
  * Gateway bot (slash commands, role assignment) — requires the optional
    `discord.py` dependency and a bot token. The command *logic* lives here
    as plain functions so it is fully unit-testable without Discord; the
    gateway glue only forwards to them.

Every AI-related message carries the standard educational disclaimer.
"""

import json
import logging
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..marketdata.base import MarketDataError, SymbolNotFound
from ..marketdata.service import MarketDataService
from ..portfolio.service import value_portfolio
from ..security import credentials
from ..storage.models import AppSetting, Portfolio

log = logging.getLogger(__name__)

WEBHOOK_PROVIDER = "discord_webhook"      # encrypted credential keys
BOT_TOKEN_PROVIDER = "discord_bot_token"
EVENTS_KEY = "discord.events"             # AppSetting: JSON list of event types

DEFAULT_EVENTS = ["order_filled", "achievement", "challenge", "level_up",
                  "ai_analysis", "competition"]

AI_DISCLAIMER = "_Educational simulation — not financial advice._"

# Roadmap 7.5: automatic role assignment from platform standing.
ROLE_LADDER = [
    (1, "Beginner Investor"),
    (10, "Analyst"),
    (20, "Portfolio Manager"),
]
COMPETITION_WINNER_ROLE = "Competition Winner"


# ------------------------------------------------------------ configuration

def enabled_events(session: Session) -> list[str]:
    row = session.get(AppSetting, EVENTS_KEY)
    if row is None or not row.value:
        return list(DEFAULT_EVENTS)
    return json.loads(row.value)


def set_enabled_events(session: Session, events: list[str]) -> None:
    row = session.get(AppSetting, EVENTS_KEY)
    if row is None:
        row = AppSetting(key=EVENTS_KEY)
        session.add(row)
    row.value = json.dumps(events)


# ------------------------------------------------------------ notifications

def render_event(event_type: str, payload: dict) -> str | None:
    """Event → Discord message text. None = not a Discord-worthy event."""
    d = payload
    if event_type == "order_filled":
        return (f"📈 **Trade executed**: {d.get('side')} {d.get('quantity')} "
                f"{d.get('symbol')} @ {d.get('price')} (origin: {d.get('origin')})")
    if event_type == "achievement":
        return f"🏆 **Achievement unlocked**: {d.get('name', d.get('achievement', ''))}"
    if event_type == "challenge":
        return f"🎯 **Challenge complete**: {d.get('name', '')}"
    if event_type == "level_up":
        return f"⬆️ **Level up!** Now level {d.get('level')} — {d.get('title', '')}"
    if event_type == "ai_analysis":
        return (f"🤖 **AI analysis ready** for {d.get('symbol', 'portfolio')}\n"
                f"{AI_DISCLAIMER}")
    if event_type == "competition":
        return f"🏁 **Competition update**: {d.get('detail', '')}"
    return None


def post_webhook(url: str, content: str) -> bool:
    """Best-effort delivery; never raises into the caller."""
    try:
        resp = httpx.post(url, json={"content": content[:1900]}, timeout=5.0)
        return resp.status_code < 300
    except httpx.HTTPError as exc:
        log.warning("Discord webhook delivery failed: %s", exc)
        return False


def notify(session_factory, data_dir, event_type: str, payload: dict) -> None:
    """Called from the event bus. Opens its own session (post-commit events
    only) and stays fully isolated."""
    try:
        with session_factory() as session:
            url = credentials.load_key(session, data_dir, WEBHOOK_PROVIDER)
            if not url or event_type not in enabled_events(session):
                return
        content = render_event(event_type, payload)
    except Exception:  # noqa: BLE001
        log.exception("Discord notify config read failed")
        return
    if content:
        post_webhook(url, content)


# ------------------------------------------------------- slash command logic
# Pure functions: (session, market, args) -> reply text. The gateway bot and
# the UI preview endpoint both call these, so they're tested without Discord.

def _fmt_money(v: str | Decimal, currency: str) -> str:
    return f"{Decimal(str(v)):,.2f} {currency}"


def _user_portfolios(session: Session, username: str) -> list[Portfolio]:
    return session.scalars(
        select(Portfolio).where(Portfolio.owner == username)
        .order_by(Portfolio.created_at)
    ).all()


def command_portfolio(session: Session, market: MarketDataService,
                      username: str) -> str:
    portfolios = _user_portfolios(session, username)
    if not portfolios:
        return f"No portfolios found for **{username}**."
    lines = [f"**Portfolios of {username}**"]
    for p in portfolios[:10]:
        view = value_portfolio(p, market)
        lines.append(f"• {p.name}: {_fmt_money(view['total_value'], p.currency)} "
                     f"({len(view['holdings'])} positions)")
    return "\n".join(lines)


def command_performance(session: Session, market: MarketDataService,
                        username: str) -> str:
    portfolios = _user_portfolios(session, username)
    if not portfolios:
        return f"No portfolios found for **{username}**."
    lines = [f"**Performance — {username}**"]
    for p in portfolios[:10]:
        view = value_portfolio(p, market)
        starting = Decimal(view["starting_balance"])
        ret = ((Decimal(view["total_value"]) - starting) / starting * 100
               if starting else Decimal("0"))
        lines.append(f"• {p.name}: {ret:+.2f}% "
                     f"(day {Decimal(view['day_change']):+,.2f} {p.currency})")
    return "\n".join(lines)


def command_company(market: MarketDataService, symbol: str) -> str:
    try:
        q = market.get_quote(symbol)
    except SymbolNotFound:
        return f"Unknown symbol: **{symbol.upper()}**"
    except MarketDataError as exc:
        return f"Market data unavailable: {exc}"
    change = ""
    if q.previous_close:
        pct = (q.price - q.previous_close) / q.previous_close * 100
        change = f" ({pct:+.2f}% today)"
    return (f"**{symbol.upper()}** — {q.price} {q.currency}{change}\n"
            f"as of {q.as_of.isoformat()} via {q.provider}")


def command_leaderboard(session: Session, market: MarketDataService,
                        category: str = "highest_return") -> str:
    from ..api.leaderboards import CATEGORIES, _boards

    if category not in CATEGORIES:
        return f"Unknown category. Try one of: {', '.join(CATEGORIES)}"
    entries = _boards(session, market)[category][:10]
    if not entries:
        return "The leaderboard is empty — portfolios must opt in first."
    lines = [f"**{CATEGORIES[category]}**"]
    for e in entries:
        lines.append(f"{e['rank']}. {e['portfolio']} — {e['label']}")
    return "\n".join(lines)


def command_challenge(session: Session) -> str:
    from ..gamify.challenges import assignments_view

    rows = [a for a in assignments_view(session)
            if a["current"] and a["status"] != "COMPLETED"]
    if not rows:
        return "No open challenges right now. 🎉"
    lines = ["**Open challenges**"]
    for a in rows[:8]:
        lines.append(f"• [{a['period_type']}] {a['name']} — {a['description']} "
                     f"(+{a['xp']} XP)")
    return "\n".join(lines)


def command_summary(session: Session, market: MarketDataService,
                    username: str) -> str:
    portfolios = _user_portfolios(session, username)
    if not portfolios:
        return f"No portfolios found for **{username}**."
    total = Decimal("0")
    day = Decimal("0")
    currency = portfolios[0].currency
    for p in portfolios:
        view = value_portfolio(p, market)
        total += Decimal(view["total_value"])
        day += Decimal(view["day_change"])
    return (f"**Daily summary — {username}**\n"
            f"Total across {len(portfolios)} portfolio(s): "
            f"{total:,.2f} {currency} (day {day:+,.2f})")


COMMANDS: dict[str, str] = {
    "portfolio": "List your portfolios and values",
    "performance": "Per-portfolio returns",
    "company": "Quote a symbol",
    "leaderboard": "Show a leaderboard category",
    "challenge": "Open challenges",
    "summary": "Daily portfolio summary",
}


def run_command(session: Session, market: MarketDataService, username: str,
                command: str, arg: str = "") -> str:
    """Single dispatch point shared by the gateway bot and the UI preview."""
    if command == "portfolio":
        return command_portfolio(session, market, username)
    if command == "performance":
        return command_performance(session, market, username)
    if command == "company":
        return command_company(market, arg or "AAPL")
    if command == "leaderboard":
        return command_leaderboard(session, market, arg or "highest_return")
    if command == "challenge":
        return command_challenge(session)
    if command == "summary":
        return command_summary(session, market, username)
    return f"Unknown command. Available: {', '.join(COMMANDS)}"


# ---------------------------------------------------------- role assignment

def role_for_profile(level: int, competition_wins: int = 0) -> list[str]:
    """Automatic Discord role names for a player (roadmap 7.5)."""
    roles = []
    ladder_role = ROLE_LADDER[0][1]
    for threshold, role in ROLE_LADDER:
        if level >= threshold:
            ladder_role = role
    roles.append(ladder_role)
    if competition_wins > 0:
        roles.append(COMPETITION_WINNER_ROLE)
    return roles


# ------------------------------------------------------------- gateway bot

def gateway_available() -> bool:
    """True when the optional discord.py dependency is installed."""
    try:
        import discord  # noqa: F401

        return True
    except ImportError:
        return False


def start_gateway(session_factory, data_dir, market) -> Any | None:
    """Start the slash-command gateway bot in a daemon thread when both the
    optional dependency and a stored bot token exist. Returns the thread or
    None. Command handling forwards to run_command() above."""
    if not gateway_available():
        return None
    with session_factory() as session:
        token = credentials.load_key(session, data_dir, BOT_TOKEN_PROVIDER)
    if not token:
        return None

    import threading

    def runner() -> None:
        import asyncio

        import discord
        from discord import app_commands

        intents = discord.Intents.default()
        client = discord.Client(intents=intents)
        tree = app_commands.CommandTree(client)

        def _reply(interaction, command: str, arg: str = "") -> str:
            with session_factory() as session:
                return run_command(session, market,
                                   str(interaction.user), command, arg)

        for cmd, desc in COMMANDS.items():
            def make(cname: str):
                async def handler(interaction, arg: str = ""):
                    await interaction.response.send_message(
                        _reply(interaction, cname, arg))
                return handler
            tree.command(name=cmd, description=desc)(make(cmd))

        @client.event
        async def on_ready():
            await tree.sync()
            log.info("Discord gateway bot connected as %s", client.user)

        try:
            asyncio.run(client.start(token))
        except Exception:  # noqa: BLE001
            log.exception("Discord gateway bot stopped")

    thread = threading.Thread(target=runner, name="discord-gateway", daemon=True)
    thread.start()
    return thread
