"""Classroom module (roadmap 8.6). Depends on scenarios: assignments can pin
students to a historical replay, and students drive those replays through
the scenarios API — without it the classroom can't function as designed."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class ClassroomModule(Module):
    manifest = Manifest(
        id="classroom",
        name="Classroom Mode",
        version="1.0.0",
        description="Instructor dashboard, student portfolios, assignments "
                    "(live-market or historical-scenario, optionally "
                    "mandated), and progress tracking.",
        dependencies=["scenarios"],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.ACCESS_MULTIPLAYER],
        events_published=[],
        events_consumed=[],
        settings=[
            {"key": "classroom.enabled", "label": "Classroom mode enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Classroom", path="classroom",
                           icon="🏫"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import classroom_api
        from ..api.deps import require_module

        gate = [Depends(require_module("classroom"))]
        ctx.app.include_router(classroom_api.router, prefix=API_PREFIX,
                               dependencies=gate)
        ctx.app.include_router(classroom_api.assignment_router, prefix=API_PREFIX,
                               dependencies=gate)
