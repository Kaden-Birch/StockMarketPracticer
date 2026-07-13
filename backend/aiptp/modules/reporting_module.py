"""Reporting module: file exports (CSV/JSON/Markdown/XLSX/PDF)."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class ReportingModule(Module):
    manifest = Manifest(
        id="reporting",
        name="Reporting",
        version="1.0.0",
        description="Portfolio report exports: CSV, JSON, Markdown, XLSX, PDF "
                    "(including AI recommendation history).",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.READ_HISTORICAL_DATA],
        events_published=[],
        events_consumed=[],
        settings=[],
        ui=[UiContribution(kind="portfolio_tab", label="Exports", path="exports", icon="📄")],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import analytics as analytics_api
        from ..api.deps import require_module

        ctx.app.include_router(
            analytics_api.export_router,
            prefix=API_PREFIX,
            dependencies=[Depends(require_module("reporting"))],
        )
