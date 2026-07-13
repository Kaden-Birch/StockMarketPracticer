"""Notification channel providers (roadmap 6.11.14).

A NotificationChannel turns a (title, body) into an outbound message. In-app
inbox is always-on and handled by the Notifications module directly; these
are the *external* channels. Discord, Slack, and a generic webhook share one
HTTP implementation differing only in JSON shape. Email/Telegram/SMS slot in
here later behind the same interface.

Delivery is best-effort with a short timeout and full error isolation — a
down webhook must never break notification creation or the publishing
thread. (A durable outbound queue is a later refinement.)
"""

import logging
from typing import Protocol

import httpx

from ..security import credentials
from ..storage.models import AppSetting

log = logging.getLogger(__name__)

WEBHOOK_PROVIDER = "notify_webhook"  # credentials key for the (secret) URL
FORMAT_KEY = "notify.webhook.format"


class NotificationChannel(Protocol):
    name: str

    def send(self, title: str, body: str) -> None: ...


def _payload(fmt: str, title: str, body: str) -> dict:
    text = f"**{title}**\n{body}" if body else f"**{title}**"
    if fmt == "slack":
        return {"text": text}
    if fmt == "discord":
        return {"content": text[:1900]}
    return {"title": title, "body": body}  # generic


def send_to_channels(ctx, title: str, body: str) -> None:
    """Dispatch to every configured external channel. Isolated per channel."""
    try:
        with ctx.session_factory() as session:
            url = credentials.load_key(session, ctx.settings.data_dir, WEBHOOK_PROVIDER)
            fmt_setting = session.get(AppSetting, FORMAT_KEY)
            fmt = fmt_setting.value if fmt_setting and fmt_setting.value else "generic"
    except Exception:  # noqa: BLE001
        log.exception("Reading notification channel config failed")
        return
    if not url:
        return
    try:
        httpx.post(url, json=_payload(fmt, title, body), timeout=5.0)
    except httpx.HTTPError as exc:
        log.warning("Webhook notification delivery failed: %s", exc)
