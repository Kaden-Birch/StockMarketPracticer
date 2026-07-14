"""AI competitors module (roadmap M9). Depends on multiplayer — AI opponents
live inside regular competitions, so human/AI/mixed games share one
standings system. Contributes the patience-gated AI trading cycle to the
scheduler; every AI trade is origin=AI_AUTO, permanently marked."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class AiCompetitorsModule(Module):
    manifest = Manifest(
        id="ai_competitors",
        name="AI Competitors",
        version="1.0.0",
        description="Simulated opponents with real investing philosophies "
                    "(conservative, growth, value, dividend, technical, "
                    "quant, market timer, beginner), four difficulty levels, "
                    "full decision transparency, adaptive behavior, "
                    "tournaments, and post-game analysis.",
        dependencies=["multiplayer"],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.READ_HISTORICAL_DATA,
                     Permission.ACCESS_MULTIPLAYER],
        events_published=["order_filled"],
        events_consumed=[],
        settings=[
            {"key": "ai_competitors.enabled", "label": "AI competitors enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Tournaments",
                           path="community?tab=competitions", icon="🤖"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import aicomp_api
        from ..api.deps import require_module

        gate = [Depends(require_module("ai_competitors"))]
        ctx.app.include_router(aicomp_api.router, prefix=API_PREFIX,
                               dependencies=gate)
        ctx.app.include_router(aicomp_api.comp_router, prefix=API_PREFIX,
                               dependencies=gate)
        ctx.app.include_router(aicomp_api.tournament_router, prefix=API_PREFIX,
                               dependencies=gate)

    def start(self, ctx: AppContext) -> None:
        from ..aicomp.engine import run_ai_cycle

        ctx.scheduler_jobs.append((
            run_ai_cycle, {"trigger": "interval", "minutes": 5},
            [ctx.session_factory, ctx.market, ctx.bus], "ai_competitors",
        ))
