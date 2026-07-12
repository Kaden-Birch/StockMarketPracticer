from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..storage.models import Notification
from .deps import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


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
