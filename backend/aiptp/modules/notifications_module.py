"""Notifications module: the in-app inbox, WebSocket pushes, and outbound
channel providers (webhook: Discord/Slack/generic). Other modules never
write notifications directly — they publish events; this module renders
them into the inbox and fans out to channels."""

from ..core.modules import AppContext, Manifest, Module, Permission, UiContribution

API_PREFIX = "/api/v1"


def _render(event_type: str, d: dict) -> tuple[str, str, str | None] | None:
    """event payload -> (title, body, portfolio_id) or None to ignore."""
    if event_type == "order_filled":
        return (
            f"Order filled: {d.get('side')} {d.get('quantity')} {d.get('symbol')}",
            f"Filled at {d.get('price')} ({d.get('origin')})",
            d.get("portfolio_id"),
        )
    if event_type == "rule_fired":
        return (
            f"Automation: {d.get('rule_name')} — {d.get('result')}",
            d.get("detail", ""),
            d.get("portfolio_id"),
        )
    if event_type == "recurring_executed":
        return (
            f"Recurring purchase: {d.get('quantity')} {d.get('symbol')}",
            f"Bought at {d.get('price')}",
            d.get("portfolio_id"),
        )
    if event_type == "corporate_action":
        return (
            f"{d.get('kind', '').title()}: {d.get('symbol')}",
            f"Amount {d.get('amount')} / quantity change {d.get('quantity')}",
            d.get("portfolio_id"),
        )
    if event_type == "achievement":
        return (f"Achievement unlocked: {d.get('name')}", d.get("description", ""), d.get("portfolio_id"))
    if event_type == "challenge":
        return (f"Challenge complete: {d.get('name')}", d.get("description", ""), None)
    if event_type == "level_up":
        return (f"Level up! You reached level {d.get('level')}",
                f"New title: {d.get('title', '')}", None)
    if event_type == "ai_analysis":
        return (
            "AI analysis ready",
            f"{d.get('recommendations', 0)} recommendation(s) from {d.get('model_id')}",
            d.get("portfolio_id"),
        )
    return None


class NotificationsModule(Module):
    manifest = Manifest(
        id="notifications",
        name="Notifications",
        version="1.0.0",
        description="In-app inbox, desktop/WebSocket pushes, and outbound "
                    "channels (Discord/Slack/generic webhooks).",
        dependencies=[],
        permissions=[Permission.SEND_NOTIFICATIONS, Permission.READ_PORTFOLIO],
        events_published=["notification"],
        events_consumed=["order_filled", "rule_fired", "recurring_executed",
                          "corporate_action", "achievement", "challenge",
                          "level_up", "ai_analysis"],
        settings=[
            {"key": "notify.webhook.url", "label": "Webhook URL", "type": "secret"},
            {"key": "notify.webhook.format", "label": "Webhook format",
             "type": "choice", "choices": ["discord", "slack", "generic"]},
        ],
        ui=[UiContribution(kind="nav_item", label="Inbox", path="inbox", icon="🔔")],
    )

    def initialize(self, ctx: AppContext) -> None:
        from ..api import notifications as notifications_api
        from ..api.deps import require_module
        from fastapi import Depends

        ctx.app.include_router(
            notifications_api.router,
            prefix=API_PREFIX,
            dependencies=[Depends(require_module("notifications"))],
        )
        ctx.app.include_router(notifications_api.channels_router, prefix=API_PREFIX)

    def register_events(self, ctx: AppContext) -> None:
        def handle(event_type: str, payload: dict, session=None) -> None:
            rendered = _render(event_type, payload)
            if rendered is None:
                return
            title, body, portfolio_id = rendered
            from ..notify.service import push_notification

            if session is not None:
                # Join the publisher's open transaction — it commits.
                push_notification(session, ctx.bus, type_=event_type, title=title,
                                  body=body, portfolio_id=portfolio_id)
            else:
                # Post-commit / no-session publisher: own short transaction.
                with ctx.session_factory() as own:
                    push_notification(own, ctx.bus, type_=event_type, title=title,
                                      body=body, portfolio_id=portfolio_id)
                    own.commit()
            from ..notify.channels import send_to_channels

            send_to_channels(ctx, title, body)

        for event_type in self.manifest.events_consumed:
            ctx.bus.subscribe_internal(event_type, handle, owner="notifications")
