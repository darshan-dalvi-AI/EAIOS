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
        data = json.dumps(event)
        with self._lock:
            targets = [c["ws"] for c in self._clients.values()]
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                with self._lock:
                    self._clients.pop(id(ws), None)


hub = Hub()
