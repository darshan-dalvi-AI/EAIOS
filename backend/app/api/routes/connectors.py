"""Connectors API — configure a source, sync it into the knowledge base."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Connector, User
from app.services import audit, connectors

router = APIRouter(prefix="/connectors", tags=["connectors"])

_LABELS = {"sample": "Sample Workspace", "google_drive": "Google Drive", "gmail": "Gmail"}


def _out(c: Connector) -> dict:
    return {"id": c.id, "provider": c.provider, "label": c.label, "status": c.status,
            "detail": c.detail, "synced_count": c.synced_count,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None}


@router.get("")
def list_connectors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Connector).order_by(Connector.created_at.desc())).all()
    return [_out(c) for c in rows]


class SyncIn(BaseModel):
    provider: str = Field(pattern="^(sample|google_drive|gmail)$")
    token: str = Field(default="", max_length=4000)  # OAuth access token (drive/gmail)


@router.post("/sync")
def sync_connector(body: SyncIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Fetch from the provider and ingest into the knowledge base. Reuses (or
    creates) a Connector row per provider for this user."""
    connector = db.scalar(select(Connector).where(Connector.provider == body.provider,
                                                  Connector.owner_id == user.id))
    if connector is None:
        connector = Connector(provider=body.provider, label=_LABELS.get(body.provider, body.provider),
                              owner_id=user.id)
        db.add(connector)
        db.commit()
        db.refresh(connector)

    connector.status = "syncing"
    db.commit()
    try:
        count = connectors.sync(db, connector, body.token)
    except Exception as exc:  # noqa: BLE001 — surface provider/token errors to the UI
        connector.status = "error"
        connector.detail = str(exc)[:500]
        db.commit()
        raise HTTPException(400, f"Sync failed: {exc}") from exc

    from datetime import datetime, timezone

    connector.status = "connected"
    connector.synced_count = (connector.synced_count or 0) + count
    connector.detail = f"Ingested {count} item(s)."
    connector.last_sync_at = datetime.now(timezone.utc)
    db.commit()
    audit.log(db, "connector.sync", user.id, f"{body.provider}: +{count} docs")
    return {**_out(connector), "ingested": count}
