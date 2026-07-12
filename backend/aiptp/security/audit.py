from sqlalchemy.orm import Session

from ..storage.models import AuditLog


def audit(session: Session, actor: str, action: str, entity: str = "", detail: str = "") -> None:
    session.add(AuditLog(actor=actor, action=action, entity=entity, detail=detail))
