from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import registry
from app.agents.sql_agent import SQLAgent
from app.api.deps import get_current_user, get_db
from app.models import AgentRun, User
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
