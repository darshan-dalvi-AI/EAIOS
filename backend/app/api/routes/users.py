from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import User
from app.schemas import UserOut, UserUpdate
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if body.role is not None:
        if body.role not in {"admin", "manager", "employee"}:
            raise HTTPException(422, "Invalid role")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.full_name is not None:
        user.full_name = body.full_name
    db.commit()
    db.refresh(user)
    audit.log(db, "user.update", admin.id, f"{user.email} → role={user.role} active={user.is_active}")
    return user
