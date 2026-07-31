"""Tasks API — kanban board. Cards come from meeting action items or are
created manually; anyone can move a card, owner/admin can delete."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Task, User

router = APIRouter(prefix="/tasks", tags=["tasks"])

STATUSES = {"todo", "doing", "done"}

Status = Literal["todo", "doing", "done"]


def _out(t: Task, names: dict[str, str] | None = None) -> dict:
    """Serialise a task. ``names`` maps assignee_id → full_name, resolved once
    for the whole page — never one query per row (that was a 200-query board)."""
    assignee = names.get(t.assignee_id) if names and t.assignee_id else None
    return {"id": t.id, "title": t.title, "status": t.status, "source": t.source,
            "assignee_id": t.assignee_id, "assignee": assignee,
            "created_at": t.created_at.isoformat()}


def _assignee_names(db: Session, rows: list[Task]) -> dict[str, str]:
    """One query for every assignee on the page, instead of one per task."""
    ids = {t.assignee_id for t in rows if t.assignee_id}
    if not ids:
        return {}
    return {u.id: u.full_name
            for u in db.scalars(select(User).where(User.id.in_(ids)))}


@router.get("")
def list_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = list(db.scalars(
        select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)))
    names = _assignee_names(db, rows)
    return [_out(t, names) for t in rows]


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=400)
    # Accept a status on create, validated to the same set the board uses — so
    # an unrecognised value is a clean 422, not a silent coercion to "todo".
    status: Status = "todo"


@router.post("", status_code=201)
def create_task(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = Task(title=body.title.strip(), status=body.status, owner_id=user.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _out(t, _assignee_names(db, [t]))


class TaskPatch(BaseModel):
    status: str | None = None
    assignee_id: str | None = None
    title: str | None = Field(default=None, max_length=400)


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")

    # The board is shared, so any teammate may move a card between columns or
    # pick up work — that is the point of a kanban. Rewriting the *text* of
    # someone else's task is different: it changes what they committed to, so
    # it stays with the creator, the assignee, or a manager/admin.
    if body.title:
        may_edit = (
            t.owner_id == user.id
            or t.assignee_id == user.id
            or user.role in ("admin", "manager")
        )
        if not may_edit:
            raise HTTPException(403, "Only the creator, the assignee or a manager can rename this task")

    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(400, "status must be todo|doing|done")
        t.status = body.status
    if body.assignee_id is not None:
        t.assignee_id = body.assignee_id or None
    if body.title:
        t.title = body.title.strip()
    db.commit()
    return _out(t, _assignee_names(db, [t]))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    if t.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the creator or an admin can delete a task")
    db.delete(t)
    db.commit()
