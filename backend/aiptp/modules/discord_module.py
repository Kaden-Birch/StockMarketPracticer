"""Discord module (roadmap 7.5). Depends on the notifications module — if
notifications are disabled, Discord cascades off with it (6.11.5). Webhook
delivery works out of the box; the slash-command gateway bot additionally
needs the optional discord.py dependency and a bot token, both configured
through the UI."""

import logging

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"
log = logging.getLogger(__name__)


class DiscordModule(Module):
    manifest = Manifest(
        id="discord",
        name="Discord Integration",
        version="1.0.0",
        description="Discord notifications for trades, achievements, and AI "
                    "analyses, plus slash commands (/portfolio, /performance, "
                    "/leaderboard, ...) via an optional gateway bot. Configured "
                    "entirely in Settings — no command line.",
        dependencies=["notifications"],
        permissions=[Permission.READ_PORTFOLIO, Permission.SEND_NOTIFICATIONS],
        events_published=[],
        events_consumed=["order_filled", "achievement", "challenge",
                         "level_up", "ai_analysis", "competition"],
        settings=[
            {"key": "discord.enabled", "label": "Discord integration enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="settings_panel", label="Discord",
                           path="discord", icon="💬"),
        ],
    )

    def __init__(self) -> None:
        self._gateway = None

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import discord_api
        from ..api.deps import require_module

        ctx.app.include_router(
            discord_api.router, prefix=API_PREFIX,
            dependencies=[Depends(require_module("discord"))],
        )

    def register_events(self, ctx: AppContext) -> None:
        from ..integrations import discord as integration

        def on_event(event_type: str, payload: dict, session=None) -> None:
            # Discord delivery always uses its own session/HTTP path; a
            # passed mid-transaction session is deliberately not used for
            # outbound webhooks (network inside a write txn is a hazard).
            integration.notify(ctx.session_factory, ctx.settings.data_dir,
                               event_type, payload)

        for event_type in self.manifest.events_consumed:
            ctx.bus.subscribe_internal(event_type, on_event, owner="discord")

    def start(self, ctx: AppContext) -> None:
        from ..integrations import discord as integration

        self._gateway = integration.start_gateway(
            ctx.session_factory, ctx.settings.data_dir, ctx.market)
        if self._gateway is not None:
            log.info("Discord gateway bot thread started")
