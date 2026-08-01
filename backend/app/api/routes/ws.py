"""WebSocket endpoint — presence + live event stream.

Auth: browsers can't set headers on WebSocket, so the JWT rides the query
string (``/api/ws?token=…``). Same HMAC verification as REST.
"""
import json
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


@router.websocket("/ws/collab/{file_id}")
async def collab_endpoint(ws: WebSocket, file_id: str, token: str = Query(default="")):
    """One socket per open file — the collaborative editing channel.

    Binary frames are CRDT updates and are relayed verbatim. Text frames are
    control messages (awareness/cursors, and the client's report of the
    document text for persistence).
    """
    from app.core.collab import collab
    from app.models import ProjectFile

    payload = decode_token(token)
    if payload is None:
        await ws.close(code=4401)
        return

    with SessionLocal() as db:
        user = db.get(User, payload["sub"])
        if user is None or not user.is_active:
            await ws.close(code=4401)
            return
        if payload.get("iat", 0) < (user.token_epoch or 0):
            await ws.close(code=4401)          # session was signed out
            return
        # Tenant check: scope the session, then look the file up through it. A
        # file in another workspace simply is not found, so a room cannot be
        # joined across tenants even with a valid token and a guessed id.
        db.info["org_id"] = user.org_id
        f = db.get(ProjectFile, file_id)
        if f is None:
            await ws.close(code=4404)
            return
        org_id = user.org_id
        info = {"user_id": user.id, "name": user.full_name, "hue": user.avatar_hue}
        initial_text = f.content

    await ws.accept()
    await collab.join(file_id, org_id, ws, info)
    try:
        # Seed the client with the persisted text; it decides whether its CRDT
        # state already covers it.
        await ws.send_text(json.dumps({"type": "collab.init", "file_id": file_id,
                                       "content": initial_text}))
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if (data := msg.get("bytes")) is not None:
                await collab.broadcast_update(file_id, ws, data)
                continue
            raw = msg.get("text") or ""
            if not raw or len(raw) > 1_048_576:
                continue
            if raw == "ping":
                await ws.send_text('{"type":"pong"}')
                continue
            try:
                parsed = json.loads(raw)
            except ValueError:
                continue
            mtype = str(parsed.get("type", ""))
            if mtype == "collab.awareness":
                await collab.relay_awareness(file_id, ws, raw)
            elif mtype == "collab.text":
                await collab.note_text(file_id, str(parsed.get("content", "")), info["user_id"])
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await collab.leave(file_id, ws)


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
            # Client → server messages: ping keeps proxies alive; typing is
            # fanned out; rtc.* is point-to-point WebRTC signaling relay.
            raw = await ws.receive_text()
            if raw == "ping":
                await ws.send_text('{"type":"pong"}')
                continue
            if not raw.startswith("{") or len(raw) > 65_536:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            mtype = str(msg.get("type", ""))
            if mtype == "typing":
                hub.publish("typing", user=info["name"])
            elif mtype.startswith("rtc."):
                target = str(msg.get("to", ""))
                if not target:
                    continue
                relayed = {
                    "type": mtype,
                    "from": {"id": info["user_id"], "name": info["name"], "hue": info["hue"]},
                    "payload": msg.get("payload") or {},
                }
                reached = await hub.send_to_user(target, relayed)
                if reached == 0 and mtype == "rtc.ring":  # callee offline → tell the caller
                    await ws.send_text(json.dumps({"type": "rtc.unavailable", "payload": {"to": target}}))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await hub.disconnect(ws)
