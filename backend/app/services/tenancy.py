"""Organization (tenant) lifecycle — the default demo org, creating a company
workspace, suspending one, and deleting one with every row it owns."""
import logging
import re
from contextlib import contextmanager

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AgentRun, AuditLog, Chunk, Connector, Conversation, CustomAgent, DataTable,
    Document, Entity, EntityEdge, EntityMention, GraphCheckpoint, MemoryEntry,
    Message, Organization, SavedChart, Task, UsageEvent, User, Workflow, WorkflowRun,
)

log = logging.getLogger("eaios.tenancy")

DEFAULT_SLUG = "k-os"

# Children before parents — deleting a workspace must not trip a foreign key.
# (Every one of these carries org_id, so each is a single scoped DELETE.)
_DELETE_ORDER = [
    EntityMention, EntityEdge, Entity,      # graph leaves → entities
    Chunk,                                  # → documents
    Message, Conversation,                  # → conversations → users
    WorkflowRun, Workflow,
    GraphCheckpoint, AgentRun, MemoryEntry, AuditLog,
    CustomAgent, Connector, SavedChart, Task, UsageEvent,
    DataTable,                              # metadata; physical dt_* dropped separately
    Document,                               # after chunks
    User,                                   # last — everything above references it
]


def default_org(db: Session) -> Organization:
    """The shared demo/dev workspace — home for seeded and self-registered users
    so the platform works out of the box before anyone signs up a company."""
    org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_SLUG))
    if org is None:
        org = Organization(name="K-OS Demo Workspace", slug=DEFAULT_SLUG,
                           plan=settings.DEFAULT_PLAN)
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
    org = Organization(name=name.strip()[:160] or "Company", slug=slug,
                       plan=settings.DEFAULT_PLAN)
    db.add(org)
    # flush, NOT commit: the org's id is assigned here, but it does not become
    # permanent until the caller commits — together with the first user. If the
    # user step then fails, the whole signup rolls back instead of leaving an
    # orphaned workspace with nobody in it. Every caller (auth signup, google
    # signup, demo) adds a user and commits immediately after.
    db.flush()
    return org


@contextmanager
def unscoped(db: Session):
    """Temporarily lift tenant auto-scoping on this session.

    The platform owner lives in their *own* workspace, so the read filter would
    otherwise hide the very rows they're inspecting or deleting — a query for
    ``other_org`` on a session scoped to ``owner_org`` yields nothing. Only
    ever used by the owner console and workspace deletion, both of which are
    explicitly cross-tenant operations."""
    prev = db.info.pop("org_id", None)
    try:
        yield db
    finally:
        if prev is not None:
            db.info["org_id"] = prev


def set_status(db: Session, org: Organization, status: str) -> Organization:
    """Suspend (lock out every member, keep all data) or reactivate a workspace."""
    if status not in ("active", "suspended"):
        raise ValueError("status must be 'active' or 'suspended'")
    org.status = status
    db.commit()
    db.refresh(org)
    return org


def stats(db: Session, org_id: str) -> dict:
    """Row counts per workspace — what the owner console shows before deleting."""
    def n(model):
        with unscoped(db):
            return db.query(model).filter(model.org_id == org_id).count()
    return {
        "users": n(User), "documents": n(Document), "conversations": n(Conversation),
        "messages": n(Message), "tasks": n(Task), "workflows": n(Workflow),
        "agent_runs": n(AgentRun),
    }


def delete_org(db: Session, org: Organization) -> dict:
    """Permanently delete a workspace and everything inside it.

    Irreversible. Runs unscoped on purpose (the caller is the platform owner or
    the workspace's own admin) and deletes children before parents so no
    foreign key is left dangling. Also drops the physical ``dt_*`` tables
    materialised from that workspace's spreadsheets and removes its uploaded
    files from storage."""
    import os

    org_id, org_name = org.id, org.name
    deleted: dict[str, int] = {}

    # The caller is usually the platform owner, who lives in a *different*
    # workspace — so the read auto-filter would hide the rows we're about to
    # remove (see `unscoped`).
    with unscoped(db):
        # 1. Physical dt_* tables (created outside the ORM) + stored files,
        #    while we can still see which rows belong to this workspace.
        for (table_name,) in db.query(DataTable.table_name).filter(DataTable.org_id == org_id):
            try:
                db.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
            except Exception as exc:  # noqa: BLE001 — a stale table must not block deletion
                log.warning("dropping %s failed: %s", table_name, exc)

        try:
            from app.core import storage
            for doc_id, filename in db.query(Document.id, Document.filename).filter(
                    Document.org_id == org_id):
                storage.remove(f"{doc_id}{os.path.splitext(filename or '')[1].lower()}")
        except Exception as exc:  # noqa: BLE001 — storage cleanup is best-effort
            log.warning("storage cleanup for org %s failed: %s", org_id, exc)

        # 2. Rows, children before parents.
        for model in _DELETE_ORDER:
            result = db.execute(delete(model).where(model.org_id == org_id))
            if result.rowcount:
                deleted[model.__tablename__] = result.rowcount

        # 3. The workspace itself.
        db.execute(delete(Organization).where(Organization.id == org_id))
        db.commit()

    log.info("Deleted workspace %s (%s): %s", org_name, org_id, deleted)
    return deleted
