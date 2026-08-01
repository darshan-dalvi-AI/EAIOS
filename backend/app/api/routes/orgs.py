"""Workspace (tenant) lifecycle endpoints.

Two audiences, deliberately separated:

* **The platform owner** (the vendor running this deployment — set via
  ``PLATFORM_OWNER_EMAILS``) can list every workspace, suspend/reactivate one,
  and permanently delete one. This is the console you use to clear out test
  signups and abandoned trials.
* **A company's own admin** can permanently delete *their own* workspace, and
  only after typing its exact name — the standard SaaS "close my account".

Suspension is owner-only on purpose: a company admin suspending their own
workspace would lock everyone out with no way back in.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.config import settings
from app.models import Organization, User
from app.services import audit, industries, plans, tenancy

router = APIRouter(prefix="/orgs", tags=["workspaces"])


class StatusIn(BaseModel):
    status: str = Field(pattern="^(active|suspended)$")


class ConfirmIn(BaseModel):
    confirm: str  # must equal the workspace name, typed by the user


class IndustryIn(BaseModel):
    industry: str = Field(min_length=2, max_length=40)
    # Starter documents make every suggested question answerable on day one.
    # Opt-out rather than opt-in: a workspace that answers nothing reads as a
    # broken product, and they are one click to remove.
    with_samples: bool = True


class PlanIn(BaseModel):
    plan: str = Field(pattern="^(free|pro|business)$")


def require_owner(user: User = Depends(get_current_user)) -> User:
    """Platform-owner guard. Disabled entirely when PLATFORM_OWNER_EMAILS is
    unset, so a leaked demo login can never reach the console."""
    if not settings.is_platform_owner(user.email):
        raise HTTPException(403, "Platform owner access required")
    return user


def _out(org: Organization, stats: dict | None = None) -> dict:
    d = {"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan,
         "status": org.status, "industry": org.industry, "created_at": org.created_at}
    if stats is not None:
        d["stats"] = stats
    return d


# ── platform owner console ───────────────────────────────────────────────
@router.get("")
def list_orgs(db: Session = Depends(get_db), _: User = Depends(require_owner)):
    """Every workspace on this deployment, with how much data each holds."""
    orgs = db.scalars(select(Organization).order_by(Organization.created_at)).all()
    return [_out(o, tenancy.stats(db, o.id)) for o in orgs]


@router.patch("/{org_id}")
def set_org_status(org_id: str, body: StatusIn, db: Session = Depends(get_db),
                   owner: User = Depends(require_owner)):
    """Suspend a workspace (members can't log in; all data kept) or reactivate it."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Workspace not found")
    if org.id == owner.org_id:
        raise HTTPException(400, "You can't suspend the workspace you're signed in to")
    tenancy.set_status(db, org, body.status)
    audit.log(db, f"org.{body.status}", owner.id, f"{org.name} ({org.slug})")
    return _out(org)


@router.delete("/{org_id}")
def delete_org(org_id: str, body: ConfirmIn, db: Session = Depends(get_db),
               owner: User = Depends(require_owner)):
    """Permanently delete any workspace and everything in it. Irreversible."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Workspace not found")
    if org.id == owner.org_id:
        raise HTTPException(400, "Use the Danger Zone to delete your own workspace")
    if body.confirm.strip() != org.name:
        raise HTTPException(400, f"Type the workspace name exactly to confirm: {org.name}")
    label = f"{org.name} ({org.slug})"
    audit.log(db, "org.delete", owner.id, label)   # logged BEFORE the rows vanish
    deleted = tenancy.delete_org(db, org)
    return {"deleted": label, "rows": deleted}


# ── a company deleting itself ────────────────────────────────────────────
@router.delete("/self/workspace")
def delete_own_org(body: ConfirmIn, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    """Close this company's workspace: removes every user, document, chat, task
    and file it owns. The admin must type the workspace name to confirm."""
    if not user.org_id:
        raise HTTPException(400, "Your account isn't attached to a workspace")
    org = db.get(Organization, user.org_id)
    if org is None:
        raise HTTPException(404, "Workspace not found")
    if org.slug == tenancy.DEFAULT_SLUG:
        raise HTTPException(400, "The shared demo workspace can't be deleted")
    if body.confirm.strip() != org.name:
        raise HTTPException(400, f"Type the workspace name exactly to confirm: {org.name}")
    label = f"{org.name} ({org.slug})"
    audit.log(db, "org.delete.self", user.id, label)
    deleted = tenancy.delete_org(db, org)
    return {"deleted": label, "rows": deleted}


# ── industry personalisation ─────────────────────────────────────────────
@router.get("/industries")
def list_industries(_: User = Depends(get_current_user)):
    """The picker shown once, right after a company signs up."""
    return industries.catalogue()


@router.get("/self/apps")
def workspace_apps(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Which apps this workspace should surface, in order.

    Driven by the industry the workspace picked: a consultancy gets the code
    editor on its dock, a clinic does not. Everything else stays reachable from
    the command palette and the "All apps" drawer — this is the default
    surface, not a permission boundary.
    """
    org = db.get(Organization, user.org_id) if user.org_id else None
    industry = (org.industry if org else "") or ""
    return {"industry": industry, "apps": industries.apps_for(industry)}


@router.post("/self/industry")
def set_industry(body: IndustryIn, tasks: BackgroundTasks, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    """Configure this workspace for its industry.

    Creates specialist agents and an intake automation the company can edit or
    delete like anything else. Admin-only: it writes shared workspace objects.
    """
    if not user.org_id:
        raise HTTPException(400, "Your account isn't attached to a workspace")
    org = db.get(Organization, user.org_id)
    if org is None:
        raise HTTPException(404, "Workspace not found")
    try:
        # Indexing the new corpus is the slow part — hundreds of round trips to
        # a database in another region. It happens after the response, so "Set
        # up my workspace" returns as soon as the workspace exists.
        result = industries.apply(db, org, body.industry, user,
                                  with_samples=body.with_samples, defer=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    pending = result.pop("_pending_index", [])
    if pending:
        tasks.add_task(industries.index_documents, pending)
    audit.log(db, "org.industry", user.id, f"{org.slug} → {body.industry}")
    return result


@router.delete("/self/industry/samples")
def clear_samples(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Remove the starter documents once the customer has their own."""
    removed = industries.remove_samples(db, user)
    audit.log(db, "org.samples.remove", user.id, f"{removed} document(s)")
    return {"removed": removed}


# ── plan and limits ──────────────────────────────────────────────────────
@router.get("/self/billing")
def billing(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Current plan, live usage against every limit, and the full ladder.

    Readable by everyone in the workspace: a person who just hit a limit needs
    to see why, even if they are not the one who can change the plan.
    """
    org = db.get(Organization, user.org_id) if user.org_id else None
    return plans.describe(db, org)


@router.post("/self/billing/plan")
def change_plan(body: PlanIn, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    """Move this workspace to a plan.

    No payment processor is wired in — this is the seam a checkout webhook
    would call. It stays admin-only and audited so the change is always
    attributable.
    """
    if not user.org_id:
        raise HTTPException(400, "Your account isn't attached to a workspace")
    org = db.get(Organization, user.org_id)
    if org is None:
        raise HTTPException(404, "Workspace not found")
    previous = org.plan
    try:
        plan = plans.set_plan(db, org, body.plan)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.log(db, "org.plan", user.id, f"{org.slug}: {previous} → {plan.id}")
    # The full description comes back so the screen can repaint its usage bars
    # against the new headroom without a second round trip.
    return {"previous": previous, **plans.describe(db, org)}
