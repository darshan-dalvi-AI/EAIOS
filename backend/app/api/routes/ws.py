"""WebSocket endpoint — presence + live event stream.

Auth: browsers can't set headers on WebSocket, so the JWT rides the query
string (``/api/ws?token=…``). Same HMAC verification as REST.
"""
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.events import hub
from app.core.security import decode_token
from app.models import User

log = logging.getLogger("eaios.ws")

router = APIRouter(tags=["realtime"])


@router.get("/events/recent")
def recent_events():
    """REST replay of the live feed (used before the socket is up, and in tests)."""
    return list(hub.recent)[-50:]


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    payload = decode_token(token)
    if payload is None:
        await ws.close(code=4401)
        return

    with SessionLocal() as db:
        user = db.get(User, payload["sub"])
        if user is None or not user.is_active:
            await ws.close(code=4401)
            return
        info = {"user_id": user.id, "name": user.full_name, "hue": user.avatar_hue, "role": user.role}

    await hub.connect(ws, info)
    try:
        while True:
            # Client → server messages: ping keeps proxies alive; typing is fanned out.
            raw = await ws.receive_text()
            if raw == "ping":
                await ws.send_text('{"type":"pong"}')
            elif raw.startswith('{"type":"typing"'):
                hub.publish("typing", user=info["name"])
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await hub.disconnect(ws)
