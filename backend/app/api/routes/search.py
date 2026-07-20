"""Global search — one query across documents, passages (hybrid RAG),
entities, structured tables and the user's own chat history."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Conversation, DataTable, Document, Entity, Message, User
from app.rag.retrieval import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def global_search(q: str = Query(min_length=2, max_length=200),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    like = f"%{q}%"

    docs = db.scalars(select(Document).where(or_(Document.title.ilike(like), Document.filename.ilike(like)))
                      .order_by(Document.created_at.desc()).limit(8)).all()

    try:
        hits = hybrid_search(db, q, k=8)
    except Exception:
        hits = []
    passages = [{"doc_id": h.doc_id, "title": h.title, "section": h.section,
                 "text": (h.text or "")[:220], "score": h.score} for h in hits]

    entities = db.scalars(select(Entity).where(Entity.name.ilike(like)).order_by(Entity.mentions.desc()).limit(8)).all()

    tables = db.scalars(select(DataTable).where(or_(DataTable.table_name.ilike(like), DataTable.doc_title.ilike(like),
                                                    DataTable.title.ilike(like))).limit(6)).all()

    msgs = db.execute(
        select(Message, Conversation.title).join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id, Message.content.ilike(like))
        .order_by(Message.created_at.desc()).limit(8)
    ).all()

    return {
        "query": q,
        "documents": [{"id": d.id, "title": d.title, "doc_type": d.doc_type, "status": d.status} for d in docs],
        "passages": passages,
        "entities": [{"id": e.id, "name": e.name, "type": e.etype, "mentions": e.mentions} for e in entities],
        "tables": [{"name": t.table_name, "source": t.doc_title or t.title, "rows": t.row_count} for t in tables],
        "messages": [{"conversation": title, "role": m.role, "snippet": m.content[:180], "at": m.created_at.isoformat()} for m, title in msgs],
    }
