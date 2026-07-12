import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def event_stream(websocket: WebSocket):
    """Pushes bus events (quotes, order fills) to the client as JSON text
    frames: {"type": ..., "data": ...}."""
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
