"""Workflows API — CRUD + execution for the Automations app."""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User, Workflow, WorkflowRun
from app.schemas import WorkflowIn, WorkflowOut, WorkflowRunIn, WorkflowRunOut
from app.services import audit, workflows as engine

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _get_owned(db: Session, user: User, wf_id: str) -> Workflow:
    wf = db.get(Workflow, wf_id)
    if wf is None:
        raise HTTPException(404, "Workflow not found")
    if user.role != "admin" and wf.owner_id != user.id:
        raise HTTPException(403, "Only the owner or an admin can modify this workflow")
    return wf


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Workflow).order_by(Workflow.updated_at.desc())).all()


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(body: WorkflowIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.trigger not in ("manual", "upload", "schedule"):
        raise HTTPException(422, "trigger must be manual | upload | schedule")
    wf = Workflow(
        name=body.name, description=body.description, owner_id=user.id, trigger=body.trigger,
        nodes=json.dumps(body.nodes), edges=json.dumps(body.edges), enabled=body.enabled,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    audit.log(db, "workflow.create", user.id, body.name)
    return wf


@router.put("/{wf_id}", response_model=WorkflowOut)
def update_workflow(wf_id: str, body: WorkflowIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = _get_owned(db, user, wf_id)
    wf.name, wf.description, wf.trigger = body.name, body.description, body.trigger
    wf.nodes, wf.edges, wf.enabled = json.dumps(body.nodes), json.dumps(body.edges), body.enabled
    db.commit()
    db.refresh(wf)
    return wf


@router.delete("/{wf_id}", status_code=204)
def delete_workflow(wf_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = _get_owned(db, user, wf_id)
    db.query(WorkflowRun).filter(WorkflowRun.workflow_id == wf.id).delete()
    db.delete(wf)
    db.commit()
    audit.log(db, "workflow.delete", user.id, wf.name)


@router.post("/{wf_id}/run", response_model=WorkflowRunOut)
def run_workflow(wf_id: str, body: WorkflowRunIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = db.get(Workflow, wf_id)
    if wf is None:
        raise HTTPException(404, "Workflow not found")
    return engine.execute(db, wf, body.input, trigger="manual", actor=user)


@router.get("/{wf_id}/runs", response_model=list[WorkflowRunOut])
def workflow_runs(wf_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Workflow, wf_id) is None:
        raise HTTPException(404, "Workflow not found")
    return db.scalars(
        select(WorkflowRun).where(WorkflowRun.workflow_id == wf_id)
        .order_by(WorkflowRun.created_at.desc()).limit(20)
    ).all()
