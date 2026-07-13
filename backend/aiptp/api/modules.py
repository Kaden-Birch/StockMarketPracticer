"""Core module-management API: status, UI contributions, presets, and the
global enable/disable switch (takes effect on restart because routers and
scheduler jobs are wired at startup)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.presets import presets_view
from ..security.audit import audit
from .deps import get_db

router = APIRouter(prefix="/modules", tags=["modules"])


class ModuleToggle(BaseModel):
    enabled: bool


@router.get("")
def list_modules(request: Request, session: Session = Depends(get_db)):
    manager = request.app.state.module_manager
    return {
        "modules": manager.status(session),
        "presets": presets_view(),
    }


@router.put("/{module_id}")
def toggle_module(
    module_id: str,
    body: ModuleToggle,
    request: Request,
    session: Session = Depends(get_db),
):
    manager = request.app.state.module_manager
    try:
        manager.set_enabled(session, module_id, body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module_id}")
    cascades = []
    if not body.enabled:
        cascades = manager.dependents_of(module_id)
    audit(session, getattr(request.state, "username", "local"),
          "module.toggle", module_id, "on" if body.enabled else "off")
    session.commit()
    return {
        "module": module_id,
        "enabled": body.enabled,
        "applies": "after restart",
        "dependents_affected": cascades,
    }
