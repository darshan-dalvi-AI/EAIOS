"""Agent Studio — no-code CRUD for custom agents, plus a test-run endpoint."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.custom_agent import CustomAgentRunner
from app.api.deps import get_current_user, get_db
from app.models import CustomAgent, User
from app.services import audit

router = APIRouter(prefix="/studio", tags=["studio"])

VALID_TOOLS = {"rag", "web"}


def _slug(name: str, db: Session) -> str:
    base = "studio_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "agent")
    slug, n = base, 2
    while db.scalar(select(CustomAgent).where(CustomAgent.slug == slug)):
        slug, n = f"{base}_{n}", n + 1
    return slug


def _out(a: CustomAgent) -> dict:
    return {"id": a.id, "slug": a.slug, "name": a.name, "description": a.description,
            "system_prompt": a.system_prompt, "tools": json.loads(a.tools or "[]"),
            "hue": a.hue, "enabled": a.enabled, "run_count": a.run_count}


class AgentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=300)
    system_prompt: str = Field(min_length=10, max_length=8000)
    tools: list[str] = Field(default_factory=list)
    hue: int = Field(default=265, ge=0, le=360)
    enabled: bool = True


@router.get("/agents")
def list_agents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(CustomAgent).order_by(CustomAgent.created_at.desc())).all()
    return [_out(a) for a in rows]


@router.post("/agents", status_code=201)
def create_agent(body: AgentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tools = [t for t in body.tools if t in VALID_TOOLS]
    agent = CustomAgent(
        slug=_slug(body.name, db), name=body.name, description=body.description,
        system_prompt=body.system_prompt, tools=json.dumps(tools), hue=body.hue,
        enabled=body.enabled, owner_id=user.id,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    audit.log(db, "studio.create", user.id, f"{agent.name} ({agent.slug})")
    return _out(agent)


@router.put("/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.get(CustomAgent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    if user.role != "admin" and agent.owner_id != user.id:
        raise HTTPException(403, "Only the owner or an admin can edit this agent")
    agent.name = body.name
    agent.description = body.description
    agent.system_prompt = body.system_prompt
    agent.tools = json.dumps([t for t in body.tools if t in VALID_TOOLS])
    agent.hue = body.hue
    agent.enabled = body.enabled
    db.commit()
    db.refresh(agent)
    return _out(agent)


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.get(CustomAgent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    if user.role != "admin" and agent.owner_id != user.id:
        raise HTTPException(403, "Only the owner or an admin can delete this agent")
    db.delete(agent)
    db.commit()


class RunIn(BaseModel):
    input: str = Field(min_length=1, max_length=8000)


@router.post("/agents/{agent_id}/run")
def run_agent(agent_id: str, body: RunIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.get(CustomAgent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    runner = CustomAgentRunner(db, user, agent)
    result = runner.run(body.input)
    agent.run_count = (agent.run_count or 0) + 1
    db.commit()
    return {"answer": result.answer, "confidence": result.confidence,
            "citations": [c.model_dump() for c in result.citations]}
