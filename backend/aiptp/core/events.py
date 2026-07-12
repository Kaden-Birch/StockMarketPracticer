"""In-process event bus. Business logic publishes; WebSocket sessions (and
later: gamification, notifications, audit) subscribe. publish() is safe to
call from worker threads — delivery hops onto the main event loop."""

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
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
