"""AI Mentor module: the grounded investment assistant, the recommendation
review queue, and the learning coach. The AI *model manager* (runtimes,
downloads, hardware) is core (roadmap 6.11.1); this module is the feature
built on top of it."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class AiMentorModule(Module):
    manifest = Manifest(
        id="ai_mentor",
        name="AI Mentor",
        version="1.0.0",
        description="Grounded portfolio analysis, recommendation review queue "
                    "with guardrails, and the learning coach.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.ACCESS_AI_MODELS],
        events_published=["ai_analysis"],
        events_consumed=[],
        settings=[],
        ui=[
            UiContribution(kind="portfolio_tab", label="AI Assistant",
                            path="assistant", icon="🤖"),
            UiContribution(kind="portfolio_tab", label="Coach", path="coach", icon="🧭"),
            UiContribution(kind="nav_item", label="Mentor", path="mentor", icon="🎓"),
        ],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import ai as ai_api
        from ..api import gamify as gamify_api
        from ..api import mentor_api
        from ..api.deps import require_module

        gate = [Depends(require_module("ai_mentor"))]
        # assistant + recommendations (portfolio-scoped)
        ctx.app.include_router(ai_api.prouter, prefix=API_PREFIX, dependencies=gate)
        # the learning coach travels with the mentor, not with gamification —
        # Learning-preset portfolios keep it.
        ctx.app.include_router(gamify_api.coach_router, prefix=API_PREFIX, dependencies=gate)
        # the persistent mentor (roadmap 8.1): deterministic behavioral
        # analysis with durable memory; LLM only narrates.
        ctx.app.include_router(mentor_api.router, prefix=API_PREFIX, dependencies=gate)
