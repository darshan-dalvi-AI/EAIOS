"""Removing a person from a workspace.

Deactivating and removing answer different questions. Deactivating says "they
cannot sign in" — the account stays, the seat is released, and everything can
be undone the moment they come back from leave. Removing says "they are gone",
and it has to decide what happens to everything they touched.

The rule here: **their work belongs to the company, their traces belong to
them.** A departing employee's uploaded contracts, the automations they built
and the tasks they raised are the company's operating knowledge, so those
transfer to the admin performing the removal rather than disappearing with the
account. Their chat history, their saved memories and the OAuth link to their
personal Google account are theirs, so those are deleted.

Getting that backwards is expensive in both directions: erasing the documents
takes the company's knowledge with the person, and inheriting their mailbox
connection hands an admin a live token to someone else's inbox.

Two things are refused outright, because both leave a workspace that cannot be
administered: removing yourself, and removing the last admin.
"""
import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    AgentRun, Connector, Conversation, CustomAgent, Document, MemoryEntry,
    Message, SavedChart, Task, UsageEvent, User, Workflow,
)

log = logging.getLogger("eaios.staff")

# Roles HR may remove. HR manages line staff; only an admin can remove an
# admin or another HR account. Mirrors HR_ASSIGNABLE in the users route.
HR_REMOVABLE = {"manager", "employee"}


class RemovalRefused(Exception):
    """The removal would leave the workspace in a state nobody can fix."""


def check_removable(db: Session, actor: User, target: User) -> None:
    """Raise if this removal must not happen. Separate from ``remove_user`` so
    the interface can grey the button out for the same reasons the server
    would refuse — one set of rules, stated once."""
    if target.id == actor.id:
        raise RemovalRefused(
            "You can't remove your own account — ask another admin, or delete "
            "the whole workspace from Settings if that's what you meant."
        )
    if actor.role == "hr" and target.role not in HR_REMOVABLE:
        raise RemovalRefused("HR can remove managers and employees, not admin or HR accounts.")
    if target.role == "admin":
        others = db.scalar(
            select(User).where(User.role == "admin", User.id != target.id, User.is_active.is_(True))
        )
        if others is None:
            raise RemovalRefused(
                "This is the last active admin. Promote someone else to admin first, "
                "otherwise nobody could manage this workspace."
            )


def removal_preview(db: Session, target: User) -> dict[str, int]:
    """What a removal would move or delete — shown before it happens, so the
    confirmation describes reality rather than reassuring in the abstract."""
    def count(model, field) -> int:
        return len(list(db.scalars(select(model).where(field == target.id))))

    return {
        "documents": count(Document, Document.owner_id),
        "automations": count(Workflow, Workflow.owner_id),
        "agents": count(CustomAgent, CustomAgent.owner_id),
        "tasks": count(Task, Task.owner_id),
        "assigned_tasks": count(Task, Task.assignee_id),
        "conversations": count(Conversation, Conversation.user_id),
        "connectors": count(Connector, Connector.owner_id),
    }


def remove_user(db: Session, actor: User, target: User) -> dict:
    """Remove someone from the workspace. Raises ``RemovalRefused`` first."""
    check_removable(db, actor, target)
    moved = removal_preview(db, target)
    email, name = target.email, target.full_name

    # ── company property: transfers to whoever did the removal ──────────
    for model, field in (
        (Document, Document.owner_id),
        (Workflow, Workflow.owner_id),
        (CustomAgent, CustomAgent.owner_id),
        (SavedChart, SavedChart.owner_id),
        (Task, Task.owner_id),
    ):
        db.execute(update(model).where(field == target.id).values(owner_id=actor.id))

    # Work assigned to them goes back to the pile rather than following them
    # out of the door — an unassigned task gets picked up, a task assigned to a
    # deleted account is invisible.
    db.execute(update(Task).where(Task.assignee_id == target.id).values(assignee_id=None))

    # Cost history survives without naming them: the totals stay honest, the
    # person does not linger in a report after they have gone.
    db.execute(update(UsageEvent).where(UsageEvent.user_id == target.id).values(user_id=None))

    # ── personal to them: deleted ───────────────────────────────────────
    conversations = list(db.scalars(select(Conversation).where(Conversation.user_id == target.id)))
    for convo in conversations:
        db.query(Message).filter(Message.conversation_id == convo.id).delete(synchronize_session=False)
        db.delete(convo)

    for model, field in ((MemoryEntry, MemoryEntry.user_id), (AgentRun, AgentRun.user_id)):
        db.query(model).filter(field == target.id).delete(synchronize_session=False)

    # Their connector holds an access token for *their* Google account. Handing
    # that to an admin would be handing over someone's mailbox, so it goes.
    db.query(Connector).filter(Connector.owner_id == target.id).delete(synchronize_session=False)

    db.delete(target)
    db.commit()

    # Written after the delete so the entry cannot claim a removal that failed.
    from app.services import audit

    audit.log(db, "user.remove", actor.id,
              f"{email} ({name}) removed by {actor.role}; "
              f"{moved['documents']} document(s), {moved['automations']} automation(s), "
              f"{moved['tasks']} task(s) reassigned")
    log.info("removed %s from workspace (by %s)", email, actor.email)
    return {"removed": email, "full_name": name, "reassigned": moved}
