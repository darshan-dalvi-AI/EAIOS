from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import AgentRun, Document, Message, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/usage")
def usage(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    since = datetime.now(timezone.utc) - timedelta(days=14)

    daily = db.execute(
        select(func.date(Message.created_at), func.count())
        .where(Message.created_at >= since)
        .group_by(func.date(Message.created_at))
        .order_by(func.date(Message.created_at))
    ).all()

    by_type = db.execute(select(Document.doc_type, func.count()).group_by(Document.doc_type)).all()
    by_agent = db.execute(select(AgentRun.agent, func.count()).group_by(AgentRun.agent)).all()

    avg_ms = db.scalar(select(func.avg(AgentRun.duration_ms))) or 0

    return {
        "messages_daily": [{"date": str(d), "count": c} for d, c in daily],
        "documents_by_type": [{"type": t, "count": c} for t, c in by_type],
        "runs_by_agent": [{"agent": a, "count": c} for a, c in by_agent],
        "avg_agent_latency_ms": round(float(avg_ms), 1),
    }
