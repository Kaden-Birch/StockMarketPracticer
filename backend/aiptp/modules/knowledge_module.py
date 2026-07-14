"""Knowledge module (roadmap M10): the investment dictionary with
three-level explanations, contextual learning suggestions, quizzes,
learning paths, interactive simulators, and grounded AI explanations —
make investing understandable."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class KnowledgeModule(Module):
    manifest = Manifest(
        id="knowledge",
        name="Knowledge Base",
        version="1.0.0",
        description="Searchable investment dictionary with beginner/"
                    "intermediate/advanced explanations, contextual learning "
                    "suggestions from your real portfolio, quizzes, learning "
                    "paths, and interactive simulators.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.READ_HISTORICAL_DATA,
                     Permission.ACCESS_AI_MODELS],
        events_published=[],
        events_consumed=[],
        settings=[
            {"key": "knowledge.enabled", "label": "Knowledge base enabled",
             "type": "bool"},
        ],
        ui=[
            UiContribution(kind="nav_item", label="Learn", path="learn",
                           icon="📚"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import learn_api
        from ..api.deps import require_module

        ctx.app.include_router(
            learn_api.router, prefix=API_PREFIX,
            dependencies=[Depends(require_module("knowledge"))],
        )
