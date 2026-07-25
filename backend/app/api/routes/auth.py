from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_token, hash_password, verify_password
from app.models import Organization, User
from app.schemas import LoginIn, RegisterIn, SignupIn, Token, UserOut
from app.services import audit, tenancy

router = APIRouter(prefix="/auth", tags=["auth"])


def _org_out(org: Organization | None) -> dict | None:
    return {"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan} if org else None


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    """Create a brand-new company workspace and its first admin. This is how a
    company onboards onto EAIOS — an isolated tenant that no other company can see."""
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "That email is already registered")
    org = tenancy.create_org(db, body.company_name)
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role="admin",                # the person who creates the workspace owns it
        avatar_hue=hash(email) % 360,
        org_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(db, "org.signup", user.id, f"{org.name} ({org.slug})")
    return {
        "token": Token(access_token=create_token(user.id, user.role)).model_dump(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "org": _org_out(org),
    }


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Self-register into the shared demo workspace (kept for the public demo).
    Real companies use /auth/signup, and admins add staff via /users."""
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "Email already registered")
    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role="employee",
        avatar_hue=hash(body.email) % 360,
        org_id=tenancy.default_org(db).id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(db, "user.register", user.id, body.email)
    return user


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.hashed_password):
        audit.log(db, "auth.failed", None, body.email, request.client.host if request.client else "")
        raise HTTPException(401, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    audit.log(db, "auth.login", user.id, ip=request.client.host if request.client else "")
    org = db.get(Organization, user.org_id) if user.org_id else None
    return {
        "token": Token(access_token=create_token(user.id, user.role)).model_dump(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "org": _org_out(org),
    }


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
