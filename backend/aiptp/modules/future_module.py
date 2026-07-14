"""Future game mode module (M11): time runs as fast as you like, forward
from today's real prices along clearly-labeled simulated paths — so a
learner can watch a strategy play out over 'years' in one sitting."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class FutureModule(Module):
    manifest = Manifest(
        id="future",
        name="Future Mode",
        version="1.0.0",
        description="Accelerated-time practice: start at today's real "
                    "prices, then fast-forward through SIMULATED price paths "
                    "statistically calibrated to each stock's real history. "
                    "Clearly labeled — never presented as real data.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.READ_HISTORICAL_DATA],
        events_published=[],
        events_consumed=[],
        settings=[
            {"key": "future.enabled", "label": "Future mode enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Future", path="future",
                           icon="🔮"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import future_api
        from ..api.deps import require_module

        ctx.app.include_router(
            future_api.router, prefix=API_PREFIX,
            dependencies=[Depends(require_module("future"))],
        )
