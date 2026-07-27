"""Throwaway workspaces for people trying the product.

A public demo has one shared workspace, which means the second visitor sees
whatever the first one uploaded. That is bad three ways: it looks broken, it
leaks whatever a stranger dropped into a box marked "try me", and the database
fills with other people's experiments.

So every visitor gets their own tenant instead. Everything inside is real —
uploads genuinely index, agents genuinely answer with citations, plan limits
genuinely apply — because a demo that fakes its best feature teaches people the
product does not work. The difference is only that the whole tenant is deleted
when it expires, so nothing survives into the next visitor's session.

Two things make this safe to expose:

* **It is an ordinary tenant.** Isolation is the same mechanism protecting real
  customers (``org_id`` auto-scoping), not a special case bolted on for the
  demo. A demo visitor cannot see a paying workspace for the same reason two
  paying workspaces cannot see each other.
* **It cannot be used to reach anything privileged.** The demo admin is an
  admin *of its own throwaway workspace* and nothing else — in particular it is
  never a platform owner, so the workspace console stays out of reach.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import Organization, User

log = logging.getLogger("eaios.demo")

# The published credentials on the sign-in screen. Signing in with any of these
# on a public deployment hands over a private sandbox rather than the shared
# workspace they name.
DEMO_EMAILS = {
    "admin@eaios.dev", "manager@eaios.dev", "employee@eaios.dev", "hr@eaios.dev",
    # Older addresses that were published before the accounts became role
    # personas. Anything already written down still opens a sandbox.
    "maya@eaios.dev", "dev@eaios.dev", "riya@eaios.dev",
}

# Roles, not people. A public sign-in screen showing real names puts those
# names in front of every visitor, and a demo persona is a job title anyway.
#
# This is also the roster every demo workspace is populated with, so it must
# hold each role exactly once — retired addresses live in _ALIASES below rather
# than here, or every sandbox would get two of somebody.
_ROLE_BY_EMAIL = {
    "admin@eaios.dev": ("admin", "System Administrator", 265),
    "hr@eaios.dev": ("hr", "People Team", 330),
    "manager@eaios.dev": ("manager", "Team Manager", 180),
    "employee@eaios.dev": ("employee", "Staff Member", 210),
}

# Addresses published before the accounts became role personas.
_ALIASES = {
    "riya@eaios.dev": "hr@eaios.dev",
    "maya@eaios.dev": "manager@eaios.dev",
    "dev@eaios.dev": "employee@eaios.dev",
}


def _persona(email: str) -> tuple[str, str, int]:
    key = email.strip().lower()
    return _ROLE_BY_EMAIL.get(_ALIASES.get(key, key), ("admin", "Demo User", 265))


def is_demo_login(email: str) -> bool:
    """Should this sign-in be sandboxed?"""
    return settings.DEMO_SANDBOX and email.strip().lower() in DEMO_EMAILS


def _expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.DEMO_TTL_MINUTES)


def start_session(db: Session, as_email: str = "admin@eaios.dev",
                  defer: list | None = None) -> User:
    """Create a private throwaway workspace and the account that owns it.

    The account is an admin so the visitor can see the whole product — hiring,
    plans, the industry setup. It is an admin of nothing but this tenant.

    Pass ``defer`` a list and the slow document indexing is appended to it
    instead of run here, so the caller can finish it after the response has
    gone out. The rows and files exist either way.
    """
    from app.services import tenancy

    role, full_name, hue = _persona(as_email)

    org = tenancy.create_org(db, "Demo Workspace")
    org.is_demo = True
    org.expires_at = _expiry()

    # This request arrived without a session, so nothing has scoped it to a
    # tenant yet. Everything created below — and every query run below, which
    # is the part that bites — has to belong to the new workspace. Without
    # this the starter corpus is skipped because an *unscoped* read finds some
    # other tenant's documents, and anything created lands unstamped.
    db.info["org_id"] = org.id

    # One password derivation, reused across the throwaway accounts. Each one
    # costs 600k PBKDF2 rounds on a shared CPU, nobody is ever given these
    # passwords, and they die with the tenant in two hours — deriving four
    # separate ones only makes a visitor wait longer for the same secret.
    throwaway = hash_password(secrets.token_urlsafe(32))

    # A unique address per session: the published one is a label on the sign-in
    # screen, not an account anyone shares.
    user = User(
        email=f"demo-{secrets.token_hex(8)}@demo.invalid",
        full_name=full_name,
        hashed_password=throwaway,
        role=role,
        avatar_hue=hue,
        org_id=org.id,
        email_verified=True,      # there is no inbox to prove; the tenant is disposable
    )
    db.add(user)

    # A demo admin needs colleagues to be worth showing: hiring, roles and the
    # people list are all empty and pointless with a single account.
    for email, (r, name, h) in _ROLE_BY_EMAIL.items():
        if r == role:
            continue
        db.add(User(
            email=f"demo-{secrets.token_hex(8)}@demo.invalid",
            full_name=name, hashed_password=throwaway,
            role=r, avatar_hue=h, org_id=org.id, email_verified=True, is_active=True,
        ))
    db.commit()             # the workspace and everyone in it, in one round trip
    db.refresh(user)

    # Something to ask questions about from the first second. The industry
    # picker still runs (org.industry stays empty) and swaps this for the
    # visitor's own field if they choose one — but skipping it must not leave
    # them staring at a workspace that answers "nothing found" to everything.
    from app.services import industries

    try:
        _, pending = industries.stage_starter_documents(db, "general", user)
        if defer is None:
            industries.index_documents(pending)
        else:
            defer.extend(pending)
    except Exception:   # noqa: BLE001 — a demo without its corpus still beats no demo
        log.warning("demo corpus failed to seed", exc_info=True)

    log.info("demo workspace %s created (expires %s)", org.slug, org.expires_at)
    return user


def expires_in_minutes(org: Organization | None) -> int | None:
    """Minutes left, for the banner. None when this is not a demo."""
    if org is None or not org.is_demo or org.expires_at is None:
        return None
    expires = org.expires_at
    if expires.tzinfo is None:        # SQLite hands back naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    return max(0, int((expires - datetime.now(timezone.utc)).total_seconds() // 60))


def sweep_expired(db: Session) -> int:
    """Delete demo workspaces past their expiry.

    Runs on the scheduler tick. Without it the throwaway tenants are only
    throwaway in principle — the point is that a stranger's uploads do not sit
    in the database indefinitely.
    """
    from app.services import tenancy

    now = datetime.now(timezone.utc)
    expired = []
    for org in db.scalars(select(Organization).where(Organization.is_demo.is_(True))):
        when = org.expires_at
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when <= now:
            expired.append(org)

    for org in expired:
        try:
            tenancy.delete_org(db, org)
        except Exception:   # noqa: BLE001 — one bad tenant must not stop the sweep
            log.warning("could not sweep demo workspace %s", org.slug, exc_info=True)
    if expired:
        log.info("swept %d expired demo workspace(s)", len(expired))
    return len(expired)
