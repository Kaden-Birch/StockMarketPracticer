"""Request-scoped current user (M7 multi-user). Set by the auth middleware;
read anywhere without threading a parameter through every call site. In
desktop mode (auth disabled) everyone is the implicit "local" user with
admin powers."""

from contextvars import ContextVar

LOCAL_USER = "local"

_current_username: ContextVar[str] = ContextVar("aiptp_username", default=LOCAL_USER)
_current_role: ContextVar[str] = ContextVar("aiptp_role", default="admin")


def set_current_user(username: str, role: str) -> None:
    _current_username.set(username)
    _current_role.set(role)


def current_username() -> str:
    return _current_username.get()


def current_role() -> str:
    return _current_role.get()


def is_admin() -> bool:
    return _current_role.get() == "admin"
