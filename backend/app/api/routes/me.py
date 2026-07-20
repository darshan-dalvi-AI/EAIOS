"""Compliance endpoints — GDPR-style self-service: export everything the
platform holds about the signed-in user, or erase it (account stays)."""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import delete as sqldelete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import AuditLog, Conversation, Document, Message, SavedChart, Task, UsageEvent, User
from app.services import audit

router = APIRouter(prefix="/me", tags=["compliance"])


@router.get("/export")
def export_my_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    convs = db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all()
    conv_out = []
    for c in convs:
        msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).all()
        conv_out.append({"title": c.title, "created_at": c.created_at.isoformat(),
                         "messages": [{"role": m.role, "content": m.content, "agent": m.agent,
                                       "citations": json.loads(m.citations or "[]"), "at": m.created_at.isoformat()} for m in msgs]})
    docs = db.scalars(select(Document).where(Document.owner_id == user.id)).all()
    tasks = db.scalars(select(Task).where(Task.owner_id == user.id)).all()
    charts = db.scalars(select(SavedChart).where(SavedChart.owner_id == user.id)).all()
    logs = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).limit(500)).all()
    audit.log(db, "compliance.export", user.id, "self-service data export")
    return {
        "user": {"email": user.email, "full_name": user.full_name, "role": user.role,
                 "created_at": user.created_at.isoformat()},
        "conversations": conv_out,
        "documents": [{"title": d.title, "filename": d.filename, "doc_type": d.doc_type,
                       "status": d.status, "tags": d.tags, "created_at": d.created_at.isoformat()} for d in docs],
        "tasks": [{"title": t.title, "status": t.status, "source": t.source, "created_at": t.created_at.isoformat()} for t in tasks],
        "pinned_charts": [{"question": c.question, "created_at": c.created_at.isoformat()} for c in charts],
        "audit_trail": [{"action": a.action, "detail": a.detail, "at": a.created_at.isoformat()} for a in logs],
    }


@router.delete("/data")
def delete_my_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Erase the user's conversational and personal artifacts. The account and
    uploaded documents remain (documents may be shared knowledge — admins
    delete those explicitly via the Knowledge app)."""
    conv_ids = [c.id for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all()]
    removed = {"conversations": len(conv_ids)}
    if conv_ids:
        db.execute(sqldelete(Message).where(Message.conversation_id.in_(conv_ids)))
        db.execute(sqldelete(Conversation).where(Conversation.id.in_(conv_ids)))
    removed["tasks"] = db.execute(sqldelete(Task).where(Task.owner_id == user.id)).rowcount or 0
    removed["pinned_charts"] = db.execute(sqldelete(SavedChart).where(SavedChart.owner_id == user.id)).rowcount or 0
    removed["usage_events"] = db.execute(sqldelete(UsageEvent).where(UsageEvent.user_id == user.id)).rowcount or 0
    db.commit()
    audit.log(db, "compliance.erase", user.id, f"self-service erase: {removed}")
    return {"removed": removed, "note": "Account and shared documents kept. Ask an admin to delete uploads or the account itself."}
