"""Multiplayer module (roadmap 7.1-7.2, 7.4): competitions, cooperative
portfolios with trade proposals and voting, and investment clubs. Optional —
a solo desktop install can switch the whole thing off."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class MultiplayerModule(Module):
    manifest = Manifest(
        id="multiplayer",
        name="Multiplayer & Community",
        version="1.0.0",
        description="Competitions with shared starting balances, cooperative "
                    "portfolios with majority-vote trade proposals, and "
                    "investment clubs with discussion boards.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.ACCESS_MULTIPLAYER],
        events_published=["order_filled"],
        events_consumed=[],
        settings=[
            {"key": "multiplayer.enabled", "label": "Multiplayer enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Community", path="community",
                           icon="👥"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import community
        from ..api.deps import require_module

        gate = Depends(require_module("multiplayer"))
        ctx.app.include_router(community.competitions_router, prefix=API_PREFIX,
                               dependencies=[gate])
        ctx.app.include_router(community.coop_router, prefix=API_PREFIX,
                               dependencies=[gate])
        ctx.app.include_router(community.clubs_router, prefix=API_PREFIX,
                               dependencies=[gate])
