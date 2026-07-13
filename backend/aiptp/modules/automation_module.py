"""Automation module: rule engine, scheduled rules, and recurring (DCA)
purchases. Reacts to watch-cycle quote events instead of being called by
the watcher directly."""

from decimal import Decimal

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


class AutomationModule(Module):
    manifest = Manifest(
        id="automation",
        name="Automation",
        version="1.0.0",
        description="Rule-based triggers (price, indicators, schedules) and "
                    "recurring purchases, running 24/7 in server mode.",
        dependencies=[],
        permissions=[Permission.READ_PORTFOLIO, Permission.MODIFY_PORTFOLIO,
                     Permission.READ_HISTORICAL_DATA],
        events_published=["rule_fired", "recurring_executed"],
        events_consumed=["watch.quotes"],
        settings=[],
        ui=[UiContribution(kind="portfolio_tab", label="Automation",
                            path="automation", icon="⚙️")],
    )

    def initialize(self, ctx: AppContext) -> None:
        from fastapi import Depends

        from ..api import automation as automation_api
        from ..api import plans as plans_api
        from ..api.deps import require_module

        gate = [Depends(require_module("automation"))]
        ctx.app.include_router(automation_api.router, prefix=API_PREFIX, dependencies=gate)
        ctx.app.include_router(plans_api.router, prefix=API_PREFIX, dependencies=gate)

    def register_events(self, ctx: AppContext) -> None:
        def on_quotes(event_type: str, payload: dict, session=None) -> None:
            from ..automation.engine import run_rules

            prices = {s: Decimal(v) for s, v in (payload.get("prices") or {}).items()}
            prev = {s: Decimal(v) for s, v in (payload.get("previous_closes") or {}).items()}
            if not prices:
                return
            # watch.quotes is published post-commit, so open our own session.
            with ctx.session_factory() as own:
                run_rules(own, ctx.market, ctx.bus, prices=prices, previous_closes=prev)
                own.commit()

        ctx.bus.subscribe_internal("watch.quotes", on_quotes, owner="automation")

    def start(self, ctx: AppContext) -> None:
        from ..automation.engine import run_scheduled_rules_cycle
        from ..trading.recurring import run_recurring_cycle

        ctx.scheduler_jobs.append((
            run_scheduled_rules_cycle, {"trigger": "interval", "seconds": 60},
            [ctx.session_factory, ctx.market, ctx.bus], "automation",
        ))
        ctx.scheduler_jobs.append((
            run_recurring_cycle, {"trigger": "interval", "seconds": 60},
            [ctx.session_factory, ctx.market, ctx.bus], "automation",
        ))
