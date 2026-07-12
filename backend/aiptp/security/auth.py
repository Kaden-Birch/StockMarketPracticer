"""Authentication (PRD §27, security v1).

Modes (AIPTP_AUTH):
  disabled — desktop default: single local user, bound to 127.0.0.1, no login.
  required — server mode: Argon2id-hashed admin account, HTTP-only session
             cookie. First run exposes /auth/setup until an account exists.
Multi-user and roles land in M6; the schema already carries `role`.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..storage.models import AuthSession, User

SESSION_COOKIE = "aiptp_session"
SESSION_TTL = timedelta(days=30)

_hasher = PasswordHasher()  # argon2id defaults


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def any_user_exists(session: Session) -> bool:
    return session.scalar(select(User.id).limit(1)) is not None


def create_user(session: Session, username: str, password: str, role: str = "admin") -> User:
    user = User(username=username.strip(), password_hash=hash_password(password), role=role)
    session.add(user)
    session.flush()
    return user


def login(session: Session, username: str, password: str) -> str | None:
    """Returns a session token on success, None on bad credentials."""
    user = session.scalar(select(User).where(User.username == username.strip()))
    if user is None or not verify_password(user.password_hash, password):
        return None
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + SESSION_TTL,
        )
    )
    return token


def logout(session: Session, token: str) -> None:
    session.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))


def user_for_token(session: Session, token: str) -> User | None:
    auth = session.get(AuthSession, _token_hash(token))
    if auth is None:
        return None
    expires = auth.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        session.delete(auth)
        return None
    return session.get(User, auth.user_id)
