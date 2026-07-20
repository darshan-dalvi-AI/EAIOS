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


# rough $/1M tokens (input+output averaged) for cost estimates in Admin
_COST_PER_M = {"llama": 0.2, "phi": 0.1, "gemini": 0.4, "deepseek": 0.3, "qwen": 0.25, "claude": 6.0, "gpt": 4.0, "mock": 0.0}


def _cost(model: str, tokens: int) -> float:
    rate = next((v for k, v in _COST_PER_M.items() if k in (model or "").lower()), 0.5)
    return round(tokens / 1_000_000 * rate, 4)


@router.get("/ai-usage")
def ai_usage(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Metering for Admin: requests + estimated tokens/cost per user and per model (30 days)."""
    from app.models import UsageEvent

    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.execute(
        select(UsageEvent.user_id, UsageEvent.model, func.count(),
               func.sum(UsageEvent.prompt_tokens + UsageEvent.completion_tokens))
        .where(UsageEvent.created_at >= since)
        .group_by(UsageEvent.user_id, UsageEvent.model)
    ).all()
    names = {u.id: u.full_name for u in db.scalars(select(User)).all()}
    by_user: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    for uid, model, count, tokens in rows:
        tokens = int(tokens or 0)
        u = by_user.setdefault(uid or "system", {"user": names.get(uid, "System"), "requests": 0, "tokens": 0, "est_cost": 0.0})
        u["requests"] += count
        u["tokens"] += tokens
        u["est_cost"] = round(u["est_cost"] + _cost(model, tokens), 4)
        m = by_model.setdefault(model or "unknown", {"model": model or "unknown", "requests": 0, "tokens": 0, "est_cost": 0.0})
        m["requests"] += count
        m["tokens"] += tokens
        m["est_cost"] = round(m["est_cost"] + _cost(model, tokens), 4)
    return {"window_days": 30, "note": "token counts estimated (~4 chars/token)",
            "by_user": sorted(by_user.values(), key=lambda x: -x["tokens"]),
            "by_model": sorted(by_model.values(), key=lambda x: -x["tokens"])}


_EVAL_SET = [
    ("annual leave days", "HR"),
    ("remote work policy", "HR"),
    ("Q3 revenue", "Financial"),
    ("kubernetes deployment", "Product"),
    ("security incident report", "Security"),
    ("onboarding checklist", "Onboarding"),
]


@router.get("/rag-eval")
def rag_eval(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Live retrieval-quality snapshot: hit-rate@3 + MRR of canned queries whose
    expected document title contains the given keyword. Same method as the CI gate."""
    from app.rag.retrieval import hybrid_search

    scored = 0
    hits = 0
    rr_total = 0.0
    for query, expect in _EVAL_SET:
        try:
            results = hybrid_search(db, query, k=5)
        except Exception:  # noqa: BLE001
            results = []
        if not results:
            continue
        scored += 1
        rank = next((i for i, r in enumerate(results) if expect.lower() in (r.title or "").lower()), None)
        if rank is not None:
            rr_total += 1.0 / (rank + 1)
            if rank < 3:
                hits += 1
    if scored == 0:
        return {"queries": 0, "hit_rate": None, "mrr": None, "note": "No indexed documents yet — upload or seed first."}
    return {"queries": scored, "hit_rate": round(hits / scored, 2), "mrr": round(rr_total / scored, 2),
            "note": "hit-rate@3 and MRR over the built-in eval set, run live against the current index"}
