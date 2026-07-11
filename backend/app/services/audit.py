"""Append-only audit trail.

Includes the granular PII flag: whenever an agent (or a graph API query)
accesses sensitive, personally identifiable entities in the Knowledge Graph
— people, emails, phone numbers — a ``pii.access`` entry is written and a
``security.pii`` event is pushed to the realtime feed so admins see it live.
"""
import json

from sqlalchemy.orm import Session

from app.models import AuditLog


def log(db: Session, action: str, user_id: str | None = None, detail: str = "", ip: str = "") -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:2000], ip=ip))
    db.commit()


def flag_pii(db: Session, user_id: str | None, source: str, entities: list[str], ip: str = "") -> None:
    """Granular privacy flag — records WHO accessed WHICH sensitive entities
    through WHAT path (e.g. 'document_agent.graph', 'graph.relate')."""
    if not entities:
        return
    detail = json.dumps({"source": source, "entities": entities[:10]})
    log(db, "pii.access", user_id, detail, ip)
    try:
        from app.core.events import hub

        hub.publish("security.pii", source=source, entities=entities[:5], user_id=user_id)
    except Exception:  # noqa: BLE001 — the audit row is the contract; the event is best-effort
        pass
