import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import create_token, hash_password, needs_rehash, verify_password
from app.models import Organization, User
from app.schemas import LoginIn, RegisterIn, SignupIn, Token, UserOut
from app.services import audit, demo, emailer, tenancy, verification
from app.services.google_auth import GoogleAuthError, verify_id_token

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)   # Google ID token
    company_name: str | None = Field(default=None, max_length=160)


class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class ResendIn(BaseModel):
    email: EmailStr


def _session_payload(user: User, org: Organization | None, extra: dict | None = None) -> dict:
    payload = {
        "token": Token(access_token=create_token(user.id, user.role)).model_dump(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "org": _org_out(org),
        "is_platform_owner": settings.is_platform_owner(user.email),
        "email_verified": user.email_verified,
        # Tells the interface to say plainly that nothing here is being kept.
        "demo": bool(org and org.is_demo),
        "demo_expires_in": demo.expires_in_minutes(org),
    }
    if extra:
        payload.update(extra)
    return payload


def _start_verification(db: Session, user: User, company: str) -> dict:
    """Issue a code and try to send it. Returns what the client needs to know."""
    code = verification.issue(db, user)
    sent = emailer.send_verification_code(user.email, code, company)
    if not sent:
        # No provider configured (local dev / demo): the code is in the server
        # log. Never returned in production — that would defeat the check.
        log_msg = f"verification code for {user.email}: {code}"
        import logging
        logging.getLogger("eaios.verify").warning(log_msg)
    return {"verification_sent": sent, "verification_required": True}


def _org_out(org: Organization | None) -> dict | None:
    if not org:
        return None
    return {"id": org.id, "name": org.name, "slug": org.slug,
            "plan": org.plan, "status": org.status, "industry": org.industry}


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    """Create a brand-new company workspace and its first admin. This is how a
    company onboards onto K-OS — an isolated tenant that no other company can see."""
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "That email is already registered")
    # A throwaway inbox can't be reached later for a reset or a renewal, so a
    # workspace registered against one is a liability rather than a lead.
    if verification.is_disposable(email):
        raise HTTPException(422, "Please use a permanent work or personal email address.")
    org = tenancy.create_org(db, body.company_name)
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role="admin",                # the person who creates the workspace owns it
        avatar_hue=hash(email) % 360,
        org_id=org.id,
    )
    user.email_verified = not settings.REQUIRE_EMAIL_VERIFICATION
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(db, "org.signup", user.id, f"{org.name} ({org.slug})")

    extra = {}
    if settings.REQUIRE_EMAIL_VERIFICATION:
        extra = _start_verification(db, user, org.name)
    return _session_payload(user, org, extra)


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


@router.post("/demo")
def start_demo(request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Hand a visitor a private throwaway workspace — no password, no signup.

    Everything inside is real. It is deleted when it expires, and a reload
    starts a new one, so nothing a stranger does here survives into anyone
    else's session.

    The starter corpus is *staged* here and indexed after the response: parsing
    and embedding three documents is hundreds of round trips to a database in
    another region, and nobody should watch a spinner for that. The rows exist
    immediately, so the workspace is complete the moment it opens; the
    documents finish indexing a few seconds later while the visitor reads.
    """
    if not settings.DEMO_SANDBOX:
        raise HTTPException(404, "The demo sandbox isn't enabled on this deployment")
    pending: list = []
    user = demo.start_session(db, defer=pending)
    if pending:
        from app.services import industries

        tasks.add_task(industries.index_documents, pending)
    org = db.get(Organization, user.org_id)
    audit.log(db, "demo.start", user.id, org.slug if org else "",
              request.client.host if request.client else "")
    return _session_payload(user, org)


@router.post("/login")
def login(body: LoginIn, request: Request, tasks: BackgroundTasks,
          db: Session = Depends(get_db)):
    # The credentials printed on the sign-in screen are an invitation, not an
    # account: on a public deployment they open a private sandbox instead of a
    # workspace every visitor would share. Checked before the password so a
    # stranger never needs the real one.
    if demo.is_demo_login(body.email):
        pending: list = []
        user = demo.start_session(db, body.email, defer=pending)
        if pending:
            from app.services import industries

            tasks.add_task(industries.index_documents, pending)
        org = db.get(Organization, user.org_id)
        audit.log(db, "demo.start", user.id, org.slug if org else "",
                  request.client.host if request.client else "")
        return _session_payload(user, org)

    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.hashed_password):
        audit.log(db, "auth.failed", None, body.email, request.client.host if request.client else "")
        raise HTTPException(401, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    org = db.get(Organization, user.org_id) if user.org_id else None
    # A suspended workspace locks out every member — data is kept, access isn't.
    if org is not None and org.status == "suspended":
        audit.log(db, "auth.suspended", user.id, org.slug)
        raise HTTPException(403, f"The workspace “{org.name}” is suspended. Contact your administrator.")
    user.last_login = datetime.now(timezone.utc)
    # Silently upgrade a hash written under an older cost — this is the only
    # point where the plaintext is available to re-derive it.
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(body.password)
    db.commit()
    audit.log(db, "auth.login", user.id, ip=request.client.host if request.client else "")
    extra = {}
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        # Signed in, but the app stays gated until the address is confirmed —
        # and a fresh code goes out so they are never stuck.
        extra = _start_verification(db, user, org.name if org else "your workspace")
    return _session_payload(user, org, extra)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout")
def logout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sign out everywhere. Tokens are stateless, so dropping the copy in one
    browser doesn't stop a copy that leaked elsewhere. Bumping the account's
    token epoch retires every token issued so far — the current one included —
    which is the revocation a stolen JWT otherwise has no answer for."""
    import time as _time

    user.token_epoch = _time.time()
    db.commit()
    audit.log(db, "auth.logout", user.id, user.email)
    return {"detail": "Signed out of all sessions."}


@router.get("/config")
def auth_config():
    """What the sign-in screen needs before anyone has signed in.

    Deliberately unauthenticated: the client id is public by design (it ships
    in every Google button on the web) and the screen that needs it is the one
    you see when you have no token. Reading it from /connectors/config, which
    requires a bearer token, meant the Google button could never appear.
    """
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID,
        "email_verification": bool(settings.REQUIRE_EMAIL_VERIFICATION),
        # So the sign-in screen only offers the demo where one actually exists,
        # rather than presenting a button that answers 404.
        "demo_sandbox": bool(settings.DEMO_SANDBOX),
    }


# ── Sign in with Google ──────────────────────────────────────────────────
@router.post("/google")
def google_auth(body: GoogleIn, request: Request, db: Session = Depends(get_db)):
    """Sign in — or create a workspace — with a Google account.

    Google has already confirmed the address, so there is nothing to email and
    nothing to expire. Works for gmail.com and for company Google Workspace
    domains, which is what a paying business signs up with.
    """
    try:
        claims = verify_id_token(body.credential)
    except GoogleAuthError as exc:
        audit.log(db, "auth.google.failed", None, str(exc)[:200],
                  request.client.host if request.client else "")
        raise HTTPException(401, str(exc)) from exc

    email = claims["email"]
    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        if not body.company_name or len(body.company_name.strip()) < 2:
            # Signing in with an unknown Google account: tell them to create a
            # workspace rather than silently making one with a guessed name.
            raise HTTPException(
                404, "No workspace found for that Google account. Create one first.")
        org = tenancy.create_org(db, body.company_name.strip())
        user = User(
            email=email,
            full_name=claims["name"],
            hashed_password=hash_password(secrets.token_urlsafe(32)),  # unusable; Google is the credential
            role="admin",
            avatar_hue=hash(email) % 360,
            org_id=org.id,
            email_verified=True,          # Google asserts it
            auth_provider="google",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        audit.log(db, "org.signup.google", user.id, f"{org.name} ({org.slug})")
    else:
        if not user.is_active:
            raise HTTPException(403, "Account disabled")
        org = db.get(Organization, user.org_id) if user.org_id else None
        if org is not None and org.status == "suspended":
            raise HTTPException(403, f"The workspace “{org.name}” is suspended. Contact your administrator.")
        # Signing in through Google proves the address as surely as a code.
        if not user.email_verified:
            user.email_verified = True
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        audit.log(db, "auth.login.google", user.id,
                  ip=request.client.host if request.client else "")

    return _session_payload(user, org)


# ── Email verification (password signups) ────────────────────────────────
@router.post("/verify")
def verify_email(body: VerifyIn, db: Session = Depends(get_db)):
    """Confirm ownership with the six-digit code we emailed."""
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None:
        # Same shape as a wrong code: revealing which addresses exist would
        # turn this into an account-enumeration oracle.
        raise HTTPException(400, "That code isn't right.")
    ok, reason = verification.check(db, user, body.code)
    if not ok:
        raise HTTPException(400, reason)
    audit.log(db, "auth.verified", user.id, user.email)
    org = db.get(Organization, user.org_id) if user.org_id else None
    return _session_payload(user, org)


@router.post("/verify/resend")
def resend_verification(body: ResendIn, db: Session = Depends(get_db)):
    """Send a fresh code. Always reports success so it cannot be used to test
    whether an address is registered."""
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is not None and not user.email_verified:
        org = db.get(Organization, user.org_id) if user.org_id else None
        _start_verification(db, user, org.name if org else "your workspace")
    return {"ok": True, "detail": "If that address needs verifying, a new code is on its way."}
