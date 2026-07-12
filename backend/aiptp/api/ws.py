import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def event_stream(websocket: WebSocket):
    """Pushes bus events (quotes, order fills, notifications) to the client
    as JSON text frames: {"type": ..., "data": ...}. WebSockets bypass HTTP
    middleware, so server-mode auth is enforced here."""
    cfg = websocket.app.state.settings
    if cfg.auth == "required":
        from ..security import auth as auth_service

        token = websocket.cookies.get(auth_service.SESSION_COOKIE)
        user = None
        if token:
            with websocket.app.state.session_factory() as session:
                user = auth_service.user_for_token(session, token)
                session.commit()
        if user is None:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    bus = websocket.app.state.bus
    queue = bus.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_text(message)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        bus.unsubscribe(queue)
