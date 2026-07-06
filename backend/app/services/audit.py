"""Append-only audit trail."""
from sqlalchemy.orm import Session

from app.models import AuditLog


def log(db: Session, action: str, user_id: str | None = None, detail: str = "", ip: str = "") -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:2000], ip=ip))
    db.commit()
