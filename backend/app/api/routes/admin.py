from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.config import settings
from app.models import AgentRun, AuditLog, Chunk, Conversation, Document, Message, User
from app.rag.vectorstore import get_vectorstore
from app.schemas import AuditOut, StatsOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    return StatsOut(
        users=count(User),
        documents=count(Document),
        chunks=count(Chunk),
        conversations=count(Conversation),
        messages=count(Message),
        agent_runs=count(AgentRun),
        vector_backend=get_vectorstore().backend_name,
        llm_provider=settings.LLM_PROVIDER,
    )


@router.get("/audit", response_model=list[AuditOut])
def audit_trail(limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()


@router.get("/config")
def model_config(admin: User = Depends(require_admin)):
    """Current AI-layer configuration with secrets masked."""
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "ollama_model": settings.OLLAMA_MODEL,
        "openai_model": settings.OPENAI_MODEL,
        "openai_key_set": bool(settings.OPENAI_API_KEY),
        "anthropic_model": settings.ANTHROPIC_MODEL,
        "anthropic_key_set": bool(settings.ANTHROPIC_API_KEY),
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_dim": settings.EMBEDDING_DIM,
        "vector_backend": get_vectorstore().backend_name,
    }
