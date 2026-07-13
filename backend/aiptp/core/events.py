"""In-process event bus (roadmap 6.11.4).

Two delivery paths from one publish():
- internal subscribers — modules register handlers per event type; each
  handler runs synchronously in the publisher's thread under its own
  try/except (module error isolation);
- WebSocket fanout — queued onto the main loop for connected clients.
"""

import asyncio
import json
import logging
from typing import Any, Callable

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._handlers: dict[str, list[tuple[str, Callable[[str, dict], None]]]] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def subscribe_internal(
        self, event_type: str, handler: Callable[[str, dict], None], owner: str = "core"
    ) -> None:
        """Register a module handler for an event type ("*" for all)."""
        self._handlers.setdefault(event_type, []).append((owner, handler))

    def publish(self, event_type: str, payload: dict[str, Any], session=None) -> None:
        """Publish an event. When the publisher is mid-transaction it passes
        its `session` so DB-writing handlers (e.g. the inbox) join that
        transaction instead of opening a second SQLite writer and
        self-deadlocking on the same thread; the publisher commits. Handlers
        must not commit a passed session."""
        # internal (module) delivery first, isolated per handler
        for pattern in (event_type, "*"):
            for owner, handler in self._handlers.get(pattern, []):
                try:
                    handler(event_type, payload, session)
                except Exception:  # noqa: BLE001 — one module must not break others
                    log.exception("Event handler from module %r failed on %s",
                                  owner, event_type)
        message = json.dumps({"type": event_type, "data": payload}, default=str)
        if self._loop is None or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._fanout, message)

    def _fanout(self, message: str) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("Dropping event for slow subscriber")
