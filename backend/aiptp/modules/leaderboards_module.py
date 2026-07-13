"""Leaderboards module (roadmap 7.3): six ranking categories over opted-in
portfolios, cached ~5 minutes. Optional and privacy-first — nothing appears
until a portfolio owner flips public_on_leaderboard."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class LeaderboardsModule(Module):
    manifest = Manifest(
        id="leaderboards",
        name="Leaderboards",
        version="1.0.0",
        description="Opt-in rankings: highest return, best risk-adjusted, "
                    "best diversification, best beginner improvement, lowest "
                    "drawdown, and best backtested strategy.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.READ_HISTORICAL_DATA],
        events_published=[],
        events_consumed=[],
        settings=[
            {"key": "leaderboards.enabled", "label": "Leaderboards enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Leaderboards",
                           path="community?tab=leaderboards", icon="🏅"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import leaderboards
        from ..api.deps import require_module

        leaderboards.invalidate_cache()  # process-level cache; fresh per boot
        ctx.app.include_router(
            leaderboards.router, prefix=API_PREFIX,
            dependencies=[Depends(require_module("leaderboards"))],
        )
