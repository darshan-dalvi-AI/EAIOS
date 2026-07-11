import json

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agents import registry
from app.agents.sql_agent import SQLAgent
from app.api.deps import get_current_user, get_db
from app.core.database import Base
from app.models import AgentRun, DataTable, User
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
