import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agents import registry
from app.agents.sql_agent import SQLAgent
from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.database import Base
from app.models import AgentRun, DataTable, Document, User
from app.schemas import AgentInfo, AgentRunOut, SQLIn, SQLOut

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentInfo])
def list_agents(user: User = Depends(get_current_user)):
    return [
        AgentInfo(id=a.id, name=a.name, description=a.description, capabilities=a.capabilities)
        for a in registry.all_agents()
    ]


@router.get("/runs", response_model=list[AgentRunOut])
def recent_runs(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(min(limit, 200))).all()


@router.post("/sql", response_model=SQLOut)
def sql_assistant(body: SQLIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Natural language → safe, read-only SQL over the platform database."""
    return SQLAgent(db, user).answer(body.question)


@router.get("/sql/schema")
def sql_schema(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Live database explorer: platform tables + structured tables extracted
    from uploaded documents (advanced parsing), with row counts."""
    out = []
    for table in Base.metadata.sorted_tables:
        try:
            count = db.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar() or 0
        except Exception:  # noqa: BLE001 — table may not exist yet
            count = 0
        out.append({"table": table.name, "rows": count, "columns": [c.name for c in table.columns]})
    for dt in db.scalars(select(DataTable).order_by(DataTable.created_at.desc()).limit(50)):
        out.append({
            "table": dt.table_name, "rows": dt.row_count,
            "columns": [c["name"] for c in json.loads(dt.columns or "[]")],
            "source": f"{dt.title} · {dt.doc_title}",
        })
    return out


# ── AI Meeting Assistant ─────────────────────────────────────────────────
class MeetingIn(BaseModel):
    transcript: str = Field(min_length=20, max_length=60_000)
    title: str = Field(default="Meeting", max_length=120)
    save_to_knowledge: bool = False


MINUTES_SYSTEM = (
    "You are the EAIOS Meeting Assistant. Turn the raw transcript into crisp minutes as markdown "
    "with EXACTLY these sections: '## Summary' (3-5 sentences), '## Decisions' (bullets), "
    "'## Action Items' (bullets formatted '- [owner] task — due'). Infer owners from speaker "
    "names when present; use 'unassigned' otherwise. No preamble."
)


def _mock_minutes(transcript: str) -> str:
    """Deterministic minutes for the mock provider — keeps demos and tests reproducible."""
    sentences = [s.strip() for s in transcript.replace("\n", " ").split(".") if s.strip()]
    actionish = [s for s in sentences if any(k in s.lower() for k in ("will ", "action", "todo", "follow up", "send", "prepare", "schedule"))]
    decisionish = [s for s in sentences if any(k in s.lower() for k in ("decided", "agree", "approved", "go with", "choose"))]
    lines = ["## Summary",
             f"The meeting covered {min(len(sentences), 5)} main points across {len(transcript.split())} words of discussion. "
             "Key threads are captured below; configure a real LLM key for reasoning-based minutes.",
             "", "## Decisions"]
    lines += [f"- {s}." for s in decisionish[:4]] or ["- No explicit decisions detected."]
    lines += ["", "## Action Items"]
    lines += [f"- [unassigned] {s}." for s in actionish[:5]] or ["- No explicit action items detected."]
    return "\n".join(lines)


@router.post("/meeting")
def meeting_minutes(
    body: MeetingIn,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Transcript → structured minutes (summary, decisions, action items).
    Optionally saves transcript + minutes into the knowledge base."""
    from app.llm.provider import get_llm, safe_complete

    if get_llm().name == "mock":
        minutes = _mock_minutes(body.transcript)
    else:
        minutes = safe_complete(MINUTES_SYSTEM, f"TRANSCRIPT:\n{body.transcript[:24_000]}\n\nMINUTES:")

    doc_id = None
    if body.save_to_knowledge:
        doc = Document(
            filename=f"{body.title.replace(' ', '_').lower()}_minutes.txt",
            title=f"{body.title} — Minutes",
            doc_type="txt",
            owner_id=user.id,
            status="queued",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        dest = os.path.join(settings.UPLOAD_DIR, f"{doc.id}.txt")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(f"# {body.title} — Minutes\n\n{minutes}\n\n# Full transcript\n\n{body.transcript}")
        from app.rag import pipeline

        tasks.add_task(pipeline.ingest_document, doc.id, dest)
        doc_id = doc.id

    from app.services import audit

    audit.log(db, "meeting.minutes", user.id, f"{body.title} ({len(body.transcript)} chars, saved={bool(doc_id)})")
    return {"minutes": minutes, "doc_id": doc_id}
