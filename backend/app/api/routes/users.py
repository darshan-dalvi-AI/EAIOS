from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.security import hash_password
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])

ROLES = {"admin", "manager", "employee"}


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin creates a teammate account ('hire'): email + password + role.
    The admin then sends those credentials to the person's real inbox."""
    email = body.email.lower().strip()
    if body.role not in ROLES:
        raise HTTPException(422, "Role must be admin, manager or employee")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with that email already exists")
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role=body.role,
        avatar_hue=hash(email) % 360,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(db, "user.create", admin.id, f"{email} role={body.role}")
    return user


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
