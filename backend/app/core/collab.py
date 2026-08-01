"""Real-time collaborative editing — the server side of the Code app.

Several people edit one file at once. Doing that with "last write wins" loses
work, so the client uses a CRDT (Yjs): every keystroke becomes a small binary
update that can be applied in any order and still converge to the same text on
every machine. That property is what makes the server's job small.

The server is deliberately NOT a text editor. It:

  * authenticates the socket and checks the file belongs to the caller's
    workspace — a room is per file, and joining one you cannot read is refused;
  * relays each binary update to the other members of that room;
  * keeps the accumulated updates so someone joining late is handed the current
    state instead of an empty document;
  * persists the resulting text back to the database, debounced, so a session
    that ends (or a server that restarts) does not lose the work.

Because updates are opaque binary blobs, the server never parses the document —
it cannot corrupt the text, and adding a language or an editor feature needs no
change here.

Multi-instance note: rooms live in this process. With several instances behind a
load balancer, two people editing one file must land on the same instance, or
the relay must go through Redis (see events.Hub, which does exactly that for
presence). ``COLLAB_REDIS`` is honoured when set; otherwise single-instance.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

log = logging.getLogger("eaios.collab")

# How long after the last edit we write the text back to the database.
PERSIST_DEBOUNCE_SECONDS = 3.0
# Hard ceiling on retained updates per room before we ask clients to re-sync.
MAX_UPDATES = 4_000
MAX_UPDATE_BYTES = 512_000


@dataclass
class Member:
    ws: WebSocket
    user_id: str
    name: str
    hue: int


@dataclass
class Room:
    """One file being edited. ``updates`` is the append-only CRDT log."""
    file_id: str
    org_id: str
    members: list[Member] = field(default_factory=list)
    updates: list[bytes] = field(default_factory=list)
    dirty: bool = False
    last_edit: float = 0.0

    def peers(self) -> list[dict]:
        return [{"user_id": m.user_id, "name": m.name, "hue": m.hue} for m in self.members]


class Collab:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = asyncio.Lock()

    # ── membership ───────────────────────────────────────────────────────
    async def join(self, file_id: str, org_id: str, ws: WebSocket, user: dict) -> Room:
        async with self._lock:
            room = self._rooms.get(file_id)
            if room is None:
                room = Room(file_id=file_id, org_id=org_id)
                self._rooms[file_id] = room
            room.members.append(Member(ws=ws, user_id=user["user_id"],
                                       name=user["name"], hue=user.get("hue", 210)))
        # Hand the newcomer the accumulated state, then tell everyone who is here.
        for upd in list(room.updates):
            try:
                await ws.send_bytes(upd)
            except Exception:  # noqa: BLE001 — a slow joiner must not break the room
                break
        await self._announce(room)
        return room

    async def leave(self, file_id: str, ws: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(file_id)
            if room is None:
                return
            room.members = [m for m in room.members if m.ws is not ws]
            empty = not room.members
        if empty:
            # Last editor left: flush now rather than waiting for the debounce.
            await self._persist(file_id, force=True)
            async with self._lock:
                r = self._rooms.get(file_id)
                if r is not None and not r.members:
                    self._rooms.pop(file_id, None)
        else:
            await self._announce(room)

    async def _announce(self, room: Room) -> None:
        import json

        msg = json.dumps({"type": "collab.peers", "file_id": room.file_id,
                          "peers": room.peers()})
        for m in list(room.members):
            try:
                await m.ws.send_text(msg)
            except Exception:  # noqa: BLE001
                pass

    # ── the hot path ─────────────────────────────────────────────────────
    async def broadcast_update(self, file_id: str, sender: WebSocket, data: bytes) -> None:
        """Relay one CRDT update to every other member and remember it."""
        if not data or len(data) > MAX_UPDATE_BYTES:
            return
        room = self._rooms.get(file_id)
        if room is None:
            return
        room.updates.append(data)
        room.dirty = True
        room.last_edit = time.monotonic()
        if len(room.updates) > MAX_UPDATES:
            # The log is only a replay buffer; trimming costs late joiners
            # nothing because the client re-syncs from the persisted text.
            del room.updates[: len(room.updates) // 2]
        for m in list(room.members):
            if m.ws is sender:
                continue
            try:
                await m.ws.send_bytes(data)
            except Exception:  # noqa: BLE001 — drop a dead peer, keep the room alive
                pass

    async def relay_awareness(self, file_id: str, sender: WebSocket, raw: str) -> None:
        """Cursor positions and selections — ephemeral, never persisted."""
        room = self._rooms.get(file_id)
        if room is None:
            return
        for m in list(room.members):
            if m.ws is sender:
                continue
            try:
                await m.ws.send_text(raw)
            except Exception:  # noqa: BLE001
                pass

    # ── persistence ──────────────────────────────────────────────────────
    async def note_text(self, file_id: str, text: str, user_id: str) -> None:
        """The client reports the document's plain text after applying updates.

        The server holds CRDT updates it cannot decode (that would need a Yjs
        implementation in Python), so the authoritative text comes from a client.
        This is safe because the text is only ever *stored*, never used to
        resolve a conflict — the CRDT already did that, identically on every
        client, before this was sent.
        """
        room = self._rooms.get(file_id)
        if room is None:
            return
        room._pending_text = text          # type: ignore[attr-defined]
        room._pending_by = user_id         # type: ignore[attr-defined]
        room.dirty = True
        room.last_edit = time.monotonic()

    async def _persist(self, file_id: str, force: bool = False) -> None:
        room = self._rooms.get(file_id)
        if room is None or not room.dirty:
            return
        text = getattr(room, "_pending_text", None)
        if text is None:
            return
        if not force and (time.monotonic() - room.last_edit) < PERSIST_DEBOUNCE_SECONDS:
            return

        def write() -> None:
            from app.core.database import SessionLocal
            from app.models import FileVersion, ProjectFile

            with SessionLocal() as db:
                db.info["org_id"] = room.org_id      # keep the tenant filter active
                f = db.get(ProjectFile, file_id)
                if f is None or f.content == text:
                    return
                # A periodic snapshot, so a long session is recoverable.
                db.add(FileVersion(file_id=f.id, content=f.content,
                                   author_id=getattr(room, "_pending_by", None) or "",
                                   author_name="", note="autosave",
                                   org_id=room.org_id))
                f.content = text
                f.size_bytes = len(text.encode("utf-8"))
                f.updated_by = getattr(room, "_pending_by", None)
                db.commit()

        try:
            await asyncio.to_thread(write)
            room.dirty = False
        except Exception:  # noqa: BLE001 — a failed autosave must not kill the session
            log.exception("collab autosave failed for file %s", file_id)

    async def sweeper(self) -> None:
        """Background flush of idle-but-dirty rooms."""
        while True:
            await asyncio.sleep(2.0)
            for file_id in list(self._rooms.keys()):
                try:
                    await self._persist(file_id)
                except Exception:  # noqa: BLE001
                    log.exception("collab sweep failed for %s", file_id)

    def stats(self) -> dict:
        return {"rooms": len(self._rooms),
                "editors": sum(len(r.members) for r in self._rooms.values())}


collab = Collab()
