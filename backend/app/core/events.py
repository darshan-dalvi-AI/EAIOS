"""Realtime event hub — WebSocket presence + live platform events.

Design:
- A single in-process ``Hub`` (Redis pub/sub can replace `_broadcast` for
  multi-replica deployments; the interface stays the same).
- Agents/pipeline/workflows run in FastAPI's threadpool (sync code), so
  ``publish`` is thread-safe: it schedules the async broadcast onto the main
  event loop captured at connect time.
- A ring buffer of recent events lets late joiners (and the REST fallback
  ``GET /api/events/recent``) replay history.

Event shape: {"type": "...", "ts": iso8601, ...payload}
Types: presence | agent.step | chat.message | doc.status | workflow.run | system
"""
import asyncio
import json
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("eaios.events")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Hub:
    def __init__(self) -> None:
        self._clients: dict[int, dict[str, Any]] = {}  # id(ws) → {ws, user_id, name, hue, role}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self.recent: deque[dict] = deque(maxlen=100)
        # Cross-instance fan-out. With one instance this stays None and every
        # broadcast is a local loop, exactly as before. With REDIS_URL set, each
        # instance publishes to a channel and re-broadcasts what it receives, so
        # two users on different instances still see each other.
        self._redis: Any = None
        self._redis_task: asyncio.Task | None = None
        self._instance_id = uuid.uuid4().hex[:12]

    CHANNEL = "k-os:events"

    async def start_redis(self) -> bool:
        """Attach the hub to Redis pub/sub if one is configured. Never fatal —
        without it the hub simply remains single-instance."""
        from app.core.config import settings

        if not settings.REDIS_URL or self._redis is not None:
            return False
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
            await self._redis.ping()
            self._redis_task = asyncio.create_task(self._redis_listener())
            log.info("realtime hub: Redis fan-out active (instance %s)", self._instance_id)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("realtime hub: Redis unavailable, staying single-instance (%s)", exc)
            self._redis = None
            return False

    async def _redis_listener(self) -> None:
        """Re-broadcast events published by OTHER instances to our own sockets."""
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(self.CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                except Exception:  # noqa: BLE001
                    continue
                if envelope.get("src") == self._instance_id:
                    continue          # our own publish, already delivered locally
                await self._broadcast_local(envelope.get("event") or {})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a dropped subscription must not kill the app
            log.exception("realtime hub: Redis listener stopped")

    # ── connection lifecycle (async, called from the ws route) ──────────
    async def connect(self, ws: WebSocket, user: dict) -> None:
        await ws.accept()
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self._clients[id(ws)] = {"ws": ws, **user}
        await self._broadcast(self._presence_event())
        # replay a short history so a fresh window isn't empty
        for ev in list(self.recent)[-20:]:
            try:
                await ws.send_text(json.dumps(ev))
            except Exception:  # noqa: BLE001
                break

    async def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.pop(id(ws), None)
        await self._broadcast(self._presence_event())

    def presence(self) -> list[dict]:
        with self._lock:
            seen: dict[str, dict] = {}
            for c in self._clients.values():
                seen[c["user_id"]] = {
                    "id": c["user_id"], "name": c["name"], "hue": c["hue"], "role": c["role"],
                }
            return list(seen.values())

    def _presence_event(self) -> dict:
        return {"type": "presence", "ts": _now_iso(), "users": self.presence()}

    # ── publishing (thread-safe; callable from sync agent code) ─────────
    def publish(self, type_: str, **payload: Any) -> None:
        event = {"type": type_, "ts": _now_iso(), **payload}
        if type_ != "presence":
            self.recent.append(event)
        loop = self._loop
        if loop is None or loop.is_closed():
            return  # no realtime clients yet — REST replay still works
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(event), loop)
        except RuntimeError:
            pass

    async def _broadcast(self, event: dict) -> None:
        """Deliver locally, then hand to Redis so other instances deliver too."""
        await self._broadcast_local(event)
        if self._redis is not None:
            try:
                await self._redis.publish(self.CHANNEL, json.dumps(
                    {"src": self._instance_id, "event": event}))
            except Exception:  # noqa: BLE001 — local delivery already happened
                pass

    async def _broadcast_local(self, event: dict) -> None:
        data = json.dumps(event)
        with self._lock:
            targets = [c["ws"] for c in self._clients.values()]
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                with self._lock:
                    self._clients.pop(id(ws), None)

    # ── targeted delivery (WebRTC signaling relay) ───────────────────────
    async def send_to_user(self, user_id: str, event: dict) -> int:
        """Deliver an event to every socket a specific user has open.
        Returns the number of sockets reached (0 → offline). NOT added to
        the ring buffer: signaling traffic is point-to-point and private."""
        data = json.dumps(event)
        with self._lock:
            targets = [c["ws"] for c in self._clients.values() if c["user_id"] == user_id]
        sent = 0
        for ws in targets:
            try:
                await ws.send_text(data)
                sent += 1
            except Exception:  # noqa: BLE001
                with self._lock:
                    self._clients.pop(id(ws), None)
        return sent


hub = Hub()
