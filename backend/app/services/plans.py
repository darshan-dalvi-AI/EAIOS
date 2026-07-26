"""Subscription plans and the limits that make them real.

A pricing page that gates nothing is a picture of a business model. These
limits are enforced at the point of action — the upload that exceeds the
document allowance is refused, the automation that needs Pro will not switch
on — so the difference between plans is something the customer experiences
rather than reads.

Three rules shaped this:

1. **Never destroy on downgrade.** Dropping to Free does not delete the 400
   documents a customer uploaded on Pro. They keep everything, they simply
   cannot add more until they are under the cap again. Deleting a paying
   customer's data because their card expired is indefensible.
2. **A limit hit is a sales conversation, not an error.** Every refusal names
   what was hit, what the current plan allows, and what the next plan allows,
   so the interface can offer the upgrade instead of a red toast.
3. **The workspace is never bricked.** Free is a genuinely usable product. If
   it is not, the trial teaches the customer that the product does not work,
   not that the plan is small.

No payment processor is wired in. ``set_plan`` is the seam a checkout webhook
would call, and the platform owner console calls it directly today.
"""
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CustomAgent, Document, Organization, User, Workflow

UNLIMITED = -1


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_month: int             # in whole currency units; 0 = free
    blurb: str
    documents: int
    custom_agents: int
    seats: int
    automations: int             # enabled workflows running unattended
    ai_daily_tokens: int
    connectors: bool
    video: bool
    audit_export: bool
    priority_support: bool
    highlights: list[str] = field(default_factory=list)


PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free", name="Free", price_month=0,
        blurb="Enough to prove it works on your own documents.",
        documents=25, custom_agents=2, seats=5, automations=0,
        ai_daily_tokens=50_000, connectors=False, video=False,
        audit_export=False, priority_support=False,
        highlights=[
            "25 documents",
            "5 people",
            "Your industry's specialist agents",
            "Hybrid search with citations",
            "Automations you can build but not run",
        ],
    ),
    "pro": Plan(
        id="pro", name="Pro", price_month=49,
        blurb="For a team that runs on this daily.",
        documents=1_000, custom_agents=UNLIMITED, seats=15, automations=10,
        ai_daily_tokens=500_000, connectors=True, video=True,
        audit_export=False, priority_support=False,
        highlights=[
            "1,000 documents",
            "15 people",
            "Unlimited custom agents",
            "10 automations running unattended",
            "Google Drive, Gmail and website connectors",
            "Video calls with automatic minutes",
        ],
    ),
    "business": Plan(
        id="business", name="Business", price_month=149,
        blurb="For when other people audit what you do.",
        documents=UNLIMITED, custom_agents=UNLIMITED, seats=UNLIMITED,
        automations=UNLIMITED, ai_daily_tokens=2_000_000, connectors=True,
        video=True, audit_export=True, priority_support=True,
        highlights=[
            "Unlimited documents and people",
            "Unlimited automations",
            "Full audit-log export",
            "Highest AI budget",
            "Priority support",
        ],
    ),
}

ORDER = ["free", "pro", "business"]

# Historic value in Organization.plan before this module existed.
_ALIASES = {"enterprise": "business", "": "free"}


def get(plan_id: str | None) -> Plan:
    key = (plan_id or "free").lower()
    return PLANS.get(_ALIASES.get(key, key), PLANS["free"])


def next_plan(plan_id: str) -> Plan | None:
    """The plan a customer would move to — what an upgrade prompt should offer."""
    current = get(plan_id).id
    idx = ORDER.index(current)
    return PLANS[ORDER[idx + 1]] if idx + 1 < len(ORDER) else None


class LimitReached(Exception):
    """A plan limit stopped an action. Carries what the interface needs to
    offer the upgrade rather than just refusing."""

    def __init__(self, limit: str, message: str, current: Plan, used: int = 0):
        super().__init__(message)
        self.limit = limit
        self.message = message
        self.plan = current
        self.used = used
        self.upgrade = next_plan(current.id)

    def as_payload(self) -> dict:
        return {
            "detail": self.message,
            "limit": self.limit,
            "used": self.used,
            "plan": self.plan.id,
            "plan_name": self.plan.name,
            "upgrade_to": self.upgrade.id if self.upgrade else None,
            "upgrade_name": self.upgrade.name if self.upgrade else None,
            "upgrade_allows": _allowance_text(self.upgrade, self.limit) if self.upgrade else None,
        }


def _fmt(value: int) -> str:
    return "unlimited" if value == UNLIMITED else f"{value:,}"


_LIMIT_FIELDS = {
    "documents": ("documents", "documents"),
    "custom_agents": ("custom_agents", "custom agents"),
    "seats": ("seats", "people"),
    "automations": ("automations", "running automations"),
}


def _allowance_text(plan: Plan, limit: str) -> str:
    attr, noun = _LIMIT_FIELDS.get(limit, (None, limit))
    if attr is None:
        return f"{plan.name} includes it"
    return f"{_fmt(getattr(plan, attr))} {noun}"


# ── usage ────────────────────────────────────────────────────────────────
def usage(db: Session) -> dict[str, int]:
    """Current consumption for the caller's workspace. The session is already
    org-scoped, so these counts cannot leak across tenants."""
    return {
        "documents": db.scalar(select(func.count()).select_from(Document)) or 0,
        "custom_agents": db.scalar(select(func.count()).select_from(CustomAgent)) or 0,
        "seats": db.scalar(select(func.count()).select_from(User)) or 0,
        "automations": db.scalar(
            select(func.count()).select_from(Workflow).where(Workflow.enabled.is_(True))
        ) or 0,
    }


def _check(plan: Plan, limit: str, used: int, adding: int = 1) -> None:
    allowed = getattr(plan, limit)
    if allowed == UNLIMITED or used + adding <= allowed:
        return
    noun = _LIMIT_FIELDS[limit][1]
    if allowed == 0:
        msg = f"{plan.name} doesn't include {noun}."
    else:
        msg = f"You've used all {allowed:,} {noun} on the {plan.name} plan."
    raise LimitReached(limit, msg, plan, used)


def enforce(db: Session, org: Organization | None, limit: str, adding: int = 1) -> None:
    """Raise ``LimitReached`` if this action would exceed the workspace's plan.

    Called immediately before the thing it guards, never at request entry —
    checking early and acting later is how you end up refusing an action that
    would have been fine, or allowing one that isn't.
    """
    plan = get(org.plan if org else None)
    _check(plan, limit, usage(db).get(limit, 0), adding)


def feature(org: Organization | None, name: str) -> bool:
    """Is a boolean feature (connectors, video, audit_export) on this plan?"""
    return bool(getattr(get(org.plan if org else None), name, False))


def require_feature(org: Organization | None, name: str, label: str) -> None:
    plan = get(org.plan if org else None)
    if getattr(plan, name, False):
        return
    raise LimitReached(name, f"{label} isn't included in the {plan.name} plan.", plan)


def set_plan(db: Session, org: Organization, plan_id: str) -> Plan:
    """Move a workspace to a plan. The seam a checkout webhook would call.

    Downgrades never delete anything — a workspace over the new cap simply
    cannot add more until it is back under it.
    """
    plan = PLANS.get(plan_id)
    if plan is None:
        raise ValueError(f"Unknown plan '{plan_id}'")
    org.plan = plan.id
    db.commit()
    return plan


def describe(db: Session, org: Organization | None) -> dict:
    """Everything the billing screen needs in one call."""
    plan = get(org.plan if org else None)
    used = usage(db)
    return {
        "plan": {
            "id": plan.id, "name": plan.name, "price_month": plan.price_month,
            "blurb": plan.blurb, "highlights": plan.highlights,
        },
        "usage": [
            {
                "key": key,
                "label": _LIMIT_FIELDS[key][1],
                "used": used.get(key, 0),
                "limit": getattr(plan, key),
                "unlimited": getattr(plan, key) == UNLIMITED,
            }
            for key in ("documents", "custom_agents", "seats", "automations")
        ],
        "features": {
            "connectors": plan.connectors, "video": plan.video,
            "audit_export": plan.audit_export, "priority_support": plan.priority_support,
            "ai_daily_tokens": plan.ai_daily_tokens,
        },
        "plans": [
            {
                "id": p.id, "name": p.name, "price_month": p.price_month, "blurb": p.blurb,
                "highlights": p.highlights, "current": p.id == plan.id,
                "documents": p.documents, "custom_agents": p.custom_agents,
                "seats": p.seats, "automations": p.automations,
                "connectors": p.connectors, "video": p.video,
                "audit_export": p.audit_export, "ai_daily_tokens": p.ai_daily_tokens,
            }
            for p in (PLANS[k] for k in ORDER)
        ],
    }
