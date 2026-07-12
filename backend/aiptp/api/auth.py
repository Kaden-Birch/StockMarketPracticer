from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import Settings
from ..security import auth as auth_service
from ..security.audit import audit
from .deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/status")
def status(request: Request, session: Session = Depends(get_db)):
    cfg = _settings(request)
    if cfg.auth != "required":
        return {"mode": "disabled", "state": "authenticated", "username": "local"}
    if not auth_service.any_user_exists(session):
        return {"mode": "required", "state": "setup_required"}
    # This endpoint is auth-exempt, so resolve the cookie directly.
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    user = auth_service.user_for_token(session, token) if token else None
    if user is not None:
        return {"mode": "required", "state": "authenticated", "username": user.username}
    return {"mode": "required", "state": "login_required"}


@router.post("/setup", status_code=201)
def setup(
    body: Credentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    cfg = _settings(request)
    if cfg.auth != "required":
        raise HTTPException(status_code=409, detail="Authentication is disabled on this deployment")
    if auth_service.any_user_exists(session):
        raise HTTPException(status_code=409, detail="Setup already completed — log in instead")
    auth_service.create_user(session, body.username, body.password)
    token = auth_service.login(session, body.username, body.password)
    audit(session, body.username, "auth.setup", "admin account created")
    session.commit()
    response.set_cookie(
        auth_service.SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=int(auth_service.SESSION_TTL.total_seconds()),
    )
    return {"username": body.username}


@router.post("/login")
def login(
    body: Credentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    cfg = _settings(request)
    if cfg.auth != "required":
        raise HTTPException(status_code=409, detail="Authentication is disabled on this deployment")
    token = auth_service.login(session, body.username, body.password)
    if token is None:
        audit(session, body.username, "auth.login_failed")
        session.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    audit(session, body.username, "auth.login")
    session.commit()
    response.set_cookie(
        auth_service.SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=int(auth_service.SESSION_TTL.total_seconds()),
    )
    return {"username": body.username}


@router.post("/logout")
def logout(request: Request, response: Response, session: Session = Depends(get_db)):
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    if token:
        auth_service.logout(session, token)
        session.commit()
    response.delete_cookie(auth_service.SESSION_COOKIE)
    return {"ok": True}
