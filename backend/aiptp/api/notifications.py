from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..notify.channels import FORMAT_KEY, WEBHOOK_PROVIDER, send_to_channels
from ..security import credentials
from ..storage.models import AppSetting, Notification
from .deps import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])
# Channel (external provider) configuration — part of the Notifications
# module's settings surface (roadmap 6.11.10, 6.11.14).
channels_router = APIRouter(prefix="/notifications/channels", tags=["notifications"])


def _view(n: Notification) -> dict:
    return {
        "id": n.id, "type": n.type, "title": n.title, "body": n.body,
        "portfolio_id": n.portfolio_id, "read": n.read,
        "created_at": n.created_at.isoformat(),
    }


@router.get("")
def list_notifications(
    unread_only: bool = False, limit: int = 50, session: Session = Depends(get_db)
):
    query = select(Notification).order_by(Notification.created_at.desc()).limit(min(limit, 200))
    if unread_only:
        query = query.where(Notification.read == False)  # noqa: E712
    unread = session.scalar(
        select(func.count(Notification.id)).where(Notification.read == False)  # noqa: E712
    )
    return {
        "unread_count": unread or 0,
        "notifications": [_view(n) for n in session.scalars(query).all()],
    }


@router.post("/read")
def mark_read(ids: list[str] | None = None, session: Session = Depends(get_db)):
    """Mark the given notifications read, or all when ids is omitted."""
    stmt = update(Notification).values(read=True)
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    session.execute(stmt)
    session.commit()
    return {"ok": True}


class WebhookConfig(BaseModel):
    url: str | None = None  # None/"" clears
    format: str = "generic"  # discord | slack | generic


@channels_router.get("")
def get_channels(request: Request, session: Session = Depends(get_db)):
    """Report configured external channels without leaking the secret URL."""
    has_url = credentials.load_key(
        session, request.app.state.settings.data_dir, WEBHOOK_PROVIDER
    ) is not None
    fmt = session.get(AppSetting, FORMAT_KEY)
    return {
        "webhook": {"configured": has_url, "format": fmt.value if fmt else "generic"},
        "available": ["discord", "slack", "generic"],
    }


@channels_router.put("/webhook")
def set_webhook(
    body: WebhookConfig, request: Request, session: Session = Depends(get_db)
):
    data_dir = request.app.state.settings.data_dir
    if body.url:
        credentials.store_key(session, data_dir, WEBHOOK_PROVIDER, body.url)
    else:
        credentials.delete_key(session, WEBHOOK_PROVIDER)
    fmt = session.get(AppSetting, FORMAT_KEY)
    if fmt is None:
        fmt = AppSetting(key=FORMAT_KEY)
        session.add(fmt)
    fmt.value = body.format
    session.commit()
    return {"configured": bool(body.url), "format": body.format}


@channels_router.post("/webhook/test")
def test_webhook(request: Request):
    """Send a test message through the configured channel."""
    from ..core.modules import AppContext

    ctx = AppContext(
        app=request.app,
        session_factory=request.app.state.session_factory,
        market=request.app.state.market,
        bus=request.app.state.bus,
        settings=request.app.state.settings,
        model_manager=request.app.state.model_manager,
        scheduler_jobs=[],
    )
    send_to_channels(ctx, "AIPTP test notification",
                     "If you can see this, your webhook channel works.")
    return {"sent": True, "note": "Best-effort — check your channel."}
