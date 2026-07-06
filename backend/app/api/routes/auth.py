from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, RegisterIn, Token, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "Email already registered")
    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role="employee",
        avatar_hue=hash(body.email) % 360,
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
    return {
        "token": Token(access_token=create_token(user.id, user.role)).model_dump(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
    }


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
