"""Notification service: persists to the in-app inbox and pushes over the
WebSocket event stream (browser/desktop notification permission handled
client-side). Email lands in M6 with multi-user."""

from sqlalchemy.orm import Session

from ..storage.models import Notification


def push_notification(
    session: Session,
    bus,
    *,
    type_: str,
    title: str,
    body: str = "",
    portfolio_id: str | None = None,
) -> Notification:
    notification = Notification(
        type=type_, title=title, body=body, portfolio_id=portfolio_id
    )
    session.add(notification)
    session.flush()
    if bus is not None:
        bus.publish(
            "notification",
            {
                "id": notification.id,
                "type": type_,
                "title": title,
                "body": body,
                "portfolio_id": portfolio_id,
            },
        )
    return notification
