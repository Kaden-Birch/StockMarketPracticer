"""Historical scenarios module (roadmap 8.2): replay real market history —
dot-com crash, 2008, COVID, the inflation cycle, the 2016-19 tech boom —
with a forward-only virtual clock and comparisons against the market, AI
strategies, and other players."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class ScenariosModule(Module):
    manifest = Manifest(
        id="scenarios",
        name="Historical Scenarios",
        version="1.0.0",
        description="Replay real historical periods (dot-com crash, 2008, "
                    "COVID, inflation cycle, tech boom) day by day with no "
                    "future knowledge, trading at genuine historical closes.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.READ_HISTORICAL_DATA],
        events_published=[],
        events_consumed=[],
        settings=[
            {"key": "scenarios.enabled", "label": "Historical scenarios enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Scenarios", path="scenarios",
                           icon="⏳"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import scenarios_api
        from ..api.deps import require_module

        ctx.app.include_router(
            scenarios_api.router, prefix=API_PREFIX,
            dependencies=[Depends(require_module("scenarios"))],
        )
