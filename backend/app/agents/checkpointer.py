"""Checkpointer — LangGraph's native ``checkpointer`` interface, backed by
the platform database (PostgreSQL in prod, SQLite in dev).

The compiled graph calls ``put()`` after every super-step, so the full
orchestration state survives crashes and restarts. If a run dies mid-graph
(LLM outage, deploy, closed laptop), the next invocation of the same thread
(= conversation) resumes from the exact node where it stopped instead of
re-running completed agents.

``MemoryCheckpointer`` keeps the same contract for tests and ephemeral use.
"""
import json
import logging
from typing import Any, Callable

log = logging.getLogger("eaios.checkpointer")

Serializer = Callable[[dict], str]
Deserializer = Callable[[str], dict]


class MemoryCheckpointer:
    """In-process checkpointer — same interface, no persistence."""

    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def put(self, thread_id: str, state: dict, next_node: Any, status: str = "running") -> None:
        prev = self.store.get(thread_id, {})
        self.store[thread_id] = {
            "state": dict(state), "next": next_node, "status": status,
            "steps": prev.get("steps", 0) + 1,
        }

    def get(self, thread_id: str) -> dict | None:
        cp = self.store.get(thread_id)
        return dict(cp) if cp else None

    def done(self, thread_id: str, state: dict) -> None:
        self.put(thread_id, state, "__end__", status="done")


class DBCheckpointer:
    """Database-backed checkpointer. Opens its own short-lived session per
    operation — graph nodes may run in worker threads, and the caller's
    session is not thread-safe. Custom ``dumps``/``loads`` let the caller
    rehydrate rich objects (e.g. pydantic Citations) on resume."""

    def __init__(self, dumps: Serializer | None = None, loads: Deserializer | None = None) -> None:
        self._dumps = dumps or (lambda s: json.dumps(s, default=str))
        self._loads = loads or json.loads

    def put(self, thread_id: str, state: dict, next_node: Any, status: str = "running") -> None:
        try:
            from app.core.database import SessionLocal
            from app.models import GraphCheckpoint

            with SessionLocal() as db:
                row = db.query(GraphCheckpoint).filter(GraphCheckpoint.thread_id == thread_id).first()
                if row is None:
                    row = GraphCheckpoint(thread_id=thread_id)
                    db.add(row)
                row.state = self._dumps(state)
                row.next_node = json.dumps(next_node)
                row.status = status
                row.steps = (row.steps or 0) + 1
                db.commit()
        except Exception:  # noqa: BLE001 — checkpointing must never break the run
            log.exception("checkpoint put failed for thread %s", thread_id)

    def get(self, thread_id: str) -> dict | None:
        try:
            from app.core.database import SessionLocal
            from app.models import GraphCheckpoint

            with SessionLocal() as db:
                row = db.query(GraphCheckpoint).filter(GraphCheckpoint.thread_id == thread_id).first()
                if row is None:
                    return None
                return {
                    "state": self._loads(row.state or "{}"),
                    "next": json.loads(row.next_node or '"__end__"'),
                    "status": row.status,
                    "steps": row.steps,
                }
        except Exception:  # noqa: BLE001
            log.exception("checkpoint get failed for thread %s", thread_id)
            return None

    def done(self, thread_id: str, state: dict) -> None:
        self.put(thread_id, state, "__end__", status="done")
