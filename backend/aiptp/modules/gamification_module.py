"""Gamification module: profile, XP, levels, achievements, challenges, and
the report card. Fully optional; the Learning and Professional presets
disable it per portfolio, and it can be switched off globally."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class GamificationModule(Module):
    manifest = Manifest(
        id="gamification",
        name="Gamification",
        version="1.0.0",
        description="Profile, categorized XP, levels and titles, achievements, "
                    "daily/weekly/monthly challenges, and the report card. "
                    "Never rewards trading volume.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.READ_HISTORICAL_DATA],
        events_published=["achievement", "challenge", "level_up"],
        events_consumed=[],
        settings=[
            {"key": "gamification.enabled", "label": "Gamification enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Profile", path="profile", icon="🏆"),
            UiContribution(kind="portfolio_tab", label="Report card",
                            path="report-card", icon="🎓"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import gamify as gamify_api
        from ..api.deps import require_module, require_preset

        gate = Depends(require_module("gamification"))
        ctx.app.include_router(gamify_api.router, prefix=API_PREFIX, dependencies=[gate])
        ctx.app.include_router(
            gamify_api.prouter,
            prefix=API_PREFIX,
            dependencies=[gate, Depends(require_preset("gamification"))],
        )

    def start(self, ctx: AppContext) -> None:
        from ..api.gamify import run_gamify_cycle

        ctx.scheduler_jobs.append((
            run_gamify_cycle, {"trigger": "interval", "minutes": 10},
            [ctx.session_factory, ctx.market, ctx.bus], "gamification",
        ))
