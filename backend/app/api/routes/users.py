from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_hr
from app.core.security import hash_password
from app.models import Organization, User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import audit, plans

router = APIRouter(prefix="/users", tags=["users"])

ROLES = {"admin", "hr", "manager", "employee"}
# Roles HR is allowed to assign / manage. Only an admin can create or touch
# admin/hr accounts — HR manages line staff, not the org's privileged users.
HR_ASSIGNABLE = {"manager", "employee"}


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), actor: User = Depends(require_admin_or_hr)):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_admin_or_hr)):
    """Create a teammate account ('hire'): email + password + role. Admin can
    create any role; HR can only create managers/employees. The creator then
    sends the credentials to the person's real inbox."""
    email = body.email.lower().strip()
    if body.role not in ROLES:
        raise HTTPException(422, "Role must be admin, hr, manager or employee")
    if actor.role == "hr" and body.role not in HR_ASSIGNABLE:
        raise HTTPException(403, "HR can only create managers and employees")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with that email already exists")
    plans.enforce(db, db.get(Organization, actor.org_id) if actor.org_id else None, "seats")
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
    audit.log(db, "user.create", actor.id, f"{email} role={body.role} by={actor.role}")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin_or_hr),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    # HR guardrails: HR manages line staff only — it can't edit admin/hr
    # accounts, and can't promote anyone into admin or hr.
    if actor.role == "hr":
        if user.role in {"admin", "hr"}:
            raise HTTPException(403, "HR cannot modify admin or HR accounts")
        if body.role is not None and body.role not in HR_ASSIGNABLE:
            raise HTTPException(403, "HR can only assign manager or employee roles")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(422, "Invalid role")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.full_name is not None:
        user.full_name = body.full_name
    db.commit()
    db.refresh(user)
    audit.log(db, "user.update", actor.id, f"{user.email} → role={user.role} active={user.is_active} by={actor.role}")
    return user
