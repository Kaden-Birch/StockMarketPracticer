"""Career module (roadmap 8.3-8.5): the rank ladder from Intern Investor to
Institutional Investor, portfolio mandates with measured compliance, and the
advanced challenges (beat the market, survive a recession, manage a billion,
recover from a crash)."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class CareerModule(Module):
    manifest = Manifest(
        id="career",
        name="Career Mode",
        version="1.0.0",
        description="Investment career progression: rank ladder with real "
                    "objectives (risk, benchmarks, mandates, investor "
                    "protection), portfolio mandates with compliance "
                    "reporting, and advanced challenges.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.READ_HISTORICAL_DATA],
        events_published=[],
        events_consumed=[],
        settings=[
            {"key": "career.enabled", "label": "Career mode enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Career", path="career",
                           icon="💼"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import career_api
        from ..api.deps import require_module

        gate = [Depends(require_module("career"))]
        ctx.app.include_router(career_api.router, prefix=API_PREFIX,
                               dependencies=gate)
        ctx.app.include_router(career_api.mandate_router, prefix=API_PREFIX,
                               dependencies=gate)
