from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..security import credentials
from ..security.audit import audit
from ..security.backup import backup_database, list_backups
from ..storage.models import AuditLog, ProviderCredential
from .deps import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

SUPPORTED_PROVIDERS = {"alphavantage"}


class ProviderKey(BaseModel):
    provider: str
    key: str = Field(min_length=1, max_length=200)


@router.get("/providers")
def provider_keys(request: Request, session: Session = Depends(get_db)):
    """Which providers have stored keys (never returns the secrets)."""
    stored = session.scalars(select(ProviderCredential.provider)).all()
    chain = [p.name for p in request.app.state.market.providers]
    return {"stored_keys": stored, "active_chain": chain,
            "supported": sorted(SUPPORTED_PROVIDERS)}


@router.put("/providers")
def set_provider_key(
    body: ProviderKey, request: Request, session: Session = Depends(get_db)
):
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}")
    cfg = request.app.state.settings
    credentials.store_key(session, cfg.data_dir, body.provider, body.key)
    audit(session, getattr(request.state, "username", "local"),
          "settings.provider_key", body.provider)
    session.commit()
    return {"ok": True, "note": "Key stored encrypted; joins the provider chain on next restart."}


@router.delete("/providers/{provider}", status_code=204)
def delete_provider_key(provider: str, request: Request, session: Session = Depends(get_db)):
    if not credentials.delete_key(session, provider):
        raise HTTPException(status_code=404, detail="No stored key for that provider")
    audit(session, getattr(request.state, "username", "local"),
          "settings.provider_key_deleted", provider)
    session.commit()


@router.post("/backup")
def run_backup(request: Request, session: Session = Depends(get_db)):
    cfg = request.app.state.settings
    target = backup_database(cfg.resolved_db_url(), cfg.data_dir)
    if target is None:
        raise HTTPException(status_code=422, detail="Backups are supported for SQLite databases only")
    audit(session, getattr(request.state, "username", "local"), "backup.manual", target.name)
    session.commit()
    return {"backup": target.name}


@router.get("/backups")
def backups(request: Request):
    return list_backups(request.app.state.settings.data_dir)


@router.get("/audit")
def audit_log(limit: int = 100, session: Session = Depends(get_db)):
    rows = session.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    ).all()
    return [
        {"actor": r.actor, "action": r.action, "entity": r.entity,
         "detail": r.detail, "created_at": r.created_at.isoformat()}
        for r in rows
    ]
