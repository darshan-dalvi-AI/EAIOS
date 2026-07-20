"""Tasks API — kanban board. Cards come from meeting action items or are
created manually; anyone can move a card, owner/admin can delete."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Task, User

router = APIRouter(prefix="/tasks", tags=["tasks"])

STATUSES = {"todo", "doing", "done"}


def _out(t: Task, db: Session) -> dict:
    assignee = db.get(User, t.assignee_id) if t.assignee_id else None
    return {"id": t.id, "title": t.title, "status": t.status, "source": t.source,
            "assignee_id": t.assignee_id, "assignee": assignee.full_name if assignee else None,
            "created_at": t.created_at.isoformat()}


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Task).order_by(Task.created_at.desc()).limit(200)).all()
    return [_out(t, db) for t in rows]


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=400)


@router.post("", status_code=201)
def create_task(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = Task(title=body.title.strip(), owner_id=user.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _out(t, db)


class TaskPatch(BaseModel):
    status: str | None = None
    assignee_id: str | None = None
    title: str | None = Field(default=None, max_length=400)


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(400, "status must be todo|doing|done")
        t.status = body.status
    if body.assignee_id is not None:
        t.assignee_id = body.assignee_id or None
    if body.title:
        t.title = body.title.strip()
    db.commit()
    return _out(t, db)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    if t.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the creator or an admin can delete a task")
    db.delete(t)
    db.commit()
