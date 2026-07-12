from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.config import settings
from app.models import AgentRun, AuditLog, Chunk, Conversation, Document, Message, User
from app.rag.vectorstore import get_vectorstore
from app.schemas import AuditOut, StatsOut
from app.services import audit

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
    from app.llm.provider import get_llm

    llm = get_llm()
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "active_provider": llm.name,
        "active_model": getattr(llm, "model", None),
        "openai_base_url": settings.OPENAI_BASE_URL,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "ollama_model": settings.OLLAMA_MODEL,
        "openai_model": settings.OPENAI_MODEL,
        "openai_key_set": bool(settings.OPENAI_API_KEY),
        "anthropic_model": settings.ANTHROPIC_MODEL,
        "anthropic_key_set": bool(settings.ANTHROPIC_API_KEY),
        "temperature": settings.TEMPERATURE,
        "router_mode": settings.ROUTER_MODE,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_dim": settings.EMBEDDING_DIM,
        "vector_backend": get_vectorstore().backend_name,
    }


class ModelIn(BaseModel):
    """Runtime model switch (in-memory until restart; set env vars to persist)."""
    model: str | None = Field(default=None, max_length=120)       # e.g. google/gemini-2.0-flash-001
    base_url: str | None = Field(default=None, max_length=200)    # e.g. https://openrouter.ai/api/v1
    provider: str | None = Field(default=None, max_length=20)     # auto | mock | ollama | openai | anthropic
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)


@router.post("/model")
def set_model(body: ModelIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Hot-swap the AI model without a restart — powers Settings → AI Model.

    With OpenRouter as OPENAI_BASE_URL, one key serves GPT, Claude, Gemini,
    DeepSeek, Qwen, Llama and Phi: switching is just a model-id change."""
    from app.llm.provider import get_llm, reset_llm

    if body.provider is not None:
        if body.provider not in ("auto", "mock", "ollama", "openai", "anthropic"):
            raise HTTPException(422, "provider must be auto | mock | ollama | openai | anthropic")
        settings.LLM_PROVIDER = body.provider
    if body.base_url is not None:
        if not body.base_url.startswith("https://"):
            raise HTTPException(422, "base_url must be https")
        settings.OPENAI_BASE_URL = body.base_url.rstrip("/")
    if body.model is not None and body.model.strip():
        settings.OPENAI_MODEL = body.model.strip()
    if body.temperature is not None:
        settings.TEMPERATURE = body.temperature

    reset_llm()
    llm = get_llm()
    audit.log(db, "model.switch", admin.id,
              f"{llm.name}/{getattr(llm, 'model', '?')} temp={settings.TEMPERATURE}")
    return {"active_provider": llm.name, "active_model": getattr(llm, "model", None),
            "temperature": settings.TEMPERATURE}


# ── Model Arena: side-by-side comparison ─────────────────────────────────
class CompareIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    models: list[str] = Field(min_length=2, max_length=2)  # exactly two model ids


@router.post("/compare")
def compare_models(body: CompareIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Run the same prompt against two models in parallel (via the active
    OpenAI-compatible endpoint — one OpenRouter key covers all families)
    and return both answers with latency. Powers Settings → Model Arena."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.llm.provider import complete_with

    system = "You are EAIOS, an enterprise AI assistant. Answer concisely and factually."

    def run(model: str) -> dict:
        t0 = time.perf_counter()
        try:
            answer = complete_with(model.strip(), system, body.prompt)
            return {"model": model.strip(), "ms": int((time.perf_counter() - t0) * 1000),
                    "answer": answer[:6000], "error": None}
        except Exception as exc:  # noqa: BLE001 — report per-model, don't fail the whole arena
            return {"model": model.strip(), "ms": int((time.perf_counter() - t0) * 1000),
                    "answer": "", "error": str(exc)[:300]}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, body.models))

    audit.log(db, "model.compare", admin.id, f"{body.models[0]} vs {body.models[1]}")
    return {"prompt": body.prompt, "results": results}
