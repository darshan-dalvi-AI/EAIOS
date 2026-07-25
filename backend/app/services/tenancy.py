"""Organization (tenant) helpers — the default demo org, and creating a new
company workspace with a unique slug."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization

DEFAULT_SLUG = "eaios"


def default_org(db: Session) -> Organization:
    """The shared demo/dev workspace — home for seeded and self-registered users
    so the platform works out of the box before anyone signs up a company."""
    org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_SLUG))
    if org is None:
        org = Organization(name="EAIOS Demo Workspace", slug=DEFAULT_SLUG)
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    return s or "org"


def create_org(db: Session, name: str) -> Organization:
    """Create a new company workspace with a collision-free slug."""
    base = _slugify(name)
    slug, i = base, 2
    while db.scalar(select(Organization).where(Organization.slug == slug)):
        slug = f"{base}-{i}"
        i += 1
    org = Organization(name=name.strip()[:160] or "Company", slug=slug)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org
