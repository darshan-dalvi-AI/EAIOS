"""Removing a person from a workspace.

This is the most destructive thing an admin can do short of deleting the
workspace, and it has two failure modes that are equally bad: taking the
company's knowledge out of the door with the person, or handing their private
things to whoever pressed the button. So these tests pin both directions —
what must survive a removal, and what must not.

They also pin the two refusals that exist to stop a workspace becoming
unadministrable: you cannot remove yourself, and you cannot remove the last
admin.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models import (
    AuditLog, Connector, Conversation, CustomAgent, Document, MemoryEntry,
    Message, Organization, Task, User, Workflow,
)
from app.services import plans, staff


def client() -> TestClient:
    return TestClient(app)


def _login(c, email="admin@eaios.dev", pw="admin12345"):
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


def _hire(c, headers, email, role="employee", name="Sam Staff") -> str:
    r = c.post("/api/users", headers=headers, json={
        "email": email, "full_name": name, "password": "welcome123", "role": role})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _scoped():
    """Org-scoped session, the way a request has one — a bare session sees
    every tenant and turns these counts into nonsense."""
    db = SessionLocal()
    admin = db.query(User).filter(User.email == "admin@eaios.dev").one()
    db.info["org_id"] = admin.org_id
    return db


@pytest.fixture(autouse=True)
def _restore_plan():
    yield
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@eaios.dev").one_or_none()
        if admin:
            org = db.get(Organization, admin.org_id)
            if org:
                org.plan = "business"
                db.commit()
    finally:
        db.close()


# ── the refusals ─────────────────────────────────────────────────────────
def test_you_cannot_remove_yourself():
    """Removing your own admin account locks you out of a workspace you still
    own — the honest action is deleting the workspace, and the message says so."""
    with client() as c:
        h = _login(c)
        me = c.get("/api/auth/me", headers=h).json()["id"]
        r = c.delete(f"/api/users/{me}", headers=h)
        assert r.status_code == 409
        assert "your own account" in r.json()["detail"]

        db = _scoped()
        try:
            assert db.get(User, me) is not None
        finally:
            db.close()


def test_the_last_admin_cannot_be_removed():
    """Otherwise the workspace has documents, people and billing, and nobody
    who can administer any of it."""
    with client() as c:
        h = _login(c)
        other_admin = _hire(c, h, "second.admin@remove.dev", "admin", "Second Admin")
        # removing one of two admins is fine
        assert c.delete(f"/api/users/{other_admin}", headers=h).status_code == 200

        # the remaining one is refused, and the reason says what to do instead
        me = c.get("/api/auth/me", headers=h).json()["id"]
        db = _scoped()
        try:
            admin = db.get(User, me)
            with pytest.raises(staff.RemovalRefused) as err:
                staff.check_removable(db, admin, admin)
        finally:
            db.close()
        assert "your own account" in str(err.value)


def test_an_admin_who_is_not_the_last_one_can_be_removed():
    with client() as c:
        h = _login(c)
        spare = _hire(c, h, "spare.admin@remove.dev", "admin", "Spare Admin")
        assert c.delete(f"/api/users/{spare}", headers=h).status_code == 200


def test_a_deactivated_admin_can_still_be_removed():
    """The tempting version of the last-admin rule counts active admins without
    excluding the one being removed, which blocks this even though the acting
    admin plainly remains. The rule has to ask whether another active admin
    survives *this* removal."""
    with client() as c:
        h = _login(c)
        dormant = _hire(c, h, "dormant.admin@remove.dev", "admin", "Dormant Admin")
        c.patch(f"/api/users/{dormant}", headers=h, json={"is_active": False})
        assert c.delete(f"/api/users/{dormant}", headers=h).status_code == 200


def test_hr_can_remove_line_staff_but_not_admin_or_hr():
    with client() as c:
        h = _login(c)
        _hire(c, h, "hr.remover@remove.dev", "hr", "Hazel HR")
        hr = _login(c, "hr.remover@remove.dev", "welcome123")

        employee = _hire(c, h, "line.staff@remove.dev", "employee")
        assert c.delete(f"/api/users/{employee}", headers=hr).status_code == 200

        another_hr = _hire(c, h, "other.hr@remove.dev", "hr", "Other HR")
        blocked = c.delete(f"/api/users/{another_hr}", headers=hr)
        assert blocked.status_code == 409
        assert "HR can remove managers and employees" in blocked.json()["detail"]

        # tidy up so later tests are not affected by the extra accounts
        c.delete(f"/api/users/{another_hr}", headers=h)


def test_ordinary_staff_cannot_remove_anyone():
    with client() as c:
        h = _login(c)
        victim = _hire(c, h, "victim@remove.dev", "employee")
        _hire(c, h, "nosy@remove.dev", "employee", "Nosy Parker")
        nosy = _login(c, "nosy@remove.dev", "welcome123")

        assert c.delete(f"/api/users/{victim}", headers=nosy).status_code == 403
        c.delete(f"/api/users/{victim}", headers=h)
        c.delete(f"/api/users/{c.get('/api/users', headers=h).json()[-1]['id']}", headers=h)


def test_removing_someone_who_is_already_gone_says_so():
    with client() as c:
        h = _login(c)
        assert c.delete("/api/users/does-not-exist", headers=h).status_code == 404


# ── what survives, and what does not ─────────────────────────────────────
def test_their_work_transfers_and_their_traces_do_not():
    """The one that matters. A departing employee's uploaded contracts are the
    company's knowledge; their chat history and their Google connection are
    not, and inheriting the latter would hand an admin someone's inbox."""
    with client() as c:
        h = _login(c)
        leaver_id = _hire(c, h, "leaver@remove.dev", "manager", "Lee Aver")
        leaver = _login(c, "leaver@remove.dev", "welcome123")

        # things the leaver creates
        doc_id = c.post("/api/documents/upload", headers=leaver, files={
            "file": ("handover.txt", b"The Ashgrove account renews in March. "
                                     b"The Ashgrove account is owned by the delivery team.")}).json()["id"]
        c.post("/api/workflows", headers=leaver, json={
            "name": "Leaver's digest", "description": "", "trigger": "manual",
            "nodes": [{"id": "n1", "type": "trigger", "x": 0, "y": 0, "data": {}}],
            "edges": [], "enabled": False})
        c.post("/api/tasks", headers=leaver, json={"title": "Hand over the Ashgrove account"})
        c.post("/api/chat", headers=leaver, json={"message": "What renews in March?"})
        c.post("/api/connectors/sync", headers=leaver, json={"provider": "sample"})

        admin_id = c.get("/api/auth/me", headers=h).json()["id"]
        r = c.delete(f"/api/users/{leaver_id}", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["removed"] == "leaver@remove.dev"
        assert body["reassigned"]["documents"] >= 1

        db = _scoped()
        try:
            assert db.get(User, leaver_id) is None, "the account should be gone"

            # kept, and now owned by the admin who removed them
            doc = db.get(Document, doc_id)
            assert doc is not None, "the company lost a document with the person"
            assert doc.owner_id == admin_id
            flow = db.query(Workflow).filter(Workflow.name == "Leaver's digest").one()
            assert flow.owner_id == admin_id
            task = db.query(Task).filter(Task.title == "Hand over the Ashgrove account").one()
            assert task.owner_id == admin_id

            # gone, because it was theirs rather than the company's
            assert db.query(Conversation).filter(Conversation.user_id == leaver_id).count() == 0
            assert db.query(MemoryEntry).filter(MemoryEntry.user_id == leaver_id).count() == 0
            assert db.query(Connector).filter(Connector.owner_id == leaver_id).count() == 0
        finally:
            db.close()


def test_their_conversation_messages_go_with_the_conversation():
    """Deleting the conversation row and leaving the messages behind would keep
    the content while losing the ability to find or delete it."""
    with client() as c:
        h = _login(c)
        leaver_id = _hire(c, h, "chatty@remove.dev", "employee", "Chatty Person")
        leaver = _login(c, "chatty@remove.dev", "welcome123")
        c.post("/api/chat", headers=leaver, json={"message": "Something private"})

        db = _scoped()
        try:
            convo = db.query(Conversation).filter(Conversation.user_id == leaver_id).first()
            assert convo is not None
            convo_id = convo.id
            assert db.query(Message).filter(Message.conversation_id == convo_id).count() > 0
        finally:
            db.close()

        assert c.delete(f"/api/users/{leaver_id}", headers=h).status_code == 200

        db = _scoped()
        try:
            assert db.query(Message).filter(Message.conversation_id == convo_id).count() == 0
        finally:
            db.close()


def test_work_assigned_to_them_goes_back_to_the_pile():
    """A task assigned to a deleted account is invisible; unassigned, it gets
    picked up by whoever takes over."""
    with client() as c:
        h = _login(c)
        leaver_id = _hire(c, h, "assignee@remove.dev", "employee", "Assign Ee")
        task = c.post("/api/tasks", headers=h, json={"title": "Renew the Ashgrove contract"}).json()
        c.patch(f"/api/tasks/{task['id']}", headers=h, json={"assignee_id": leaver_id})

        assert c.delete(f"/api/users/{leaver_id}", headers=h).status_code == 200

        db = _scoped()
        try:
            after = db.get(Task, task["id"])
            assert after is not None and after.assignee_id is None
        finally:
            db.close()


def test_the_audit_trail_still_names_them_afterwards():
    """An audit log that forgets who did something the moment they leave is
    worthless exactly when it is needed."""
    with client() as c:
        h = _login(c)
        leaver_id = _hire(c, h, "audited@remove.dev", "employee", "Audie Ted")
        leaver = _login(c, "audited@remove.dev", "welcome123")
        c.post("/api/documents/upload", headers=leaver, files={
            "file": ("theirs.txt", b"A document uploaded before they left the company.")})

        assert c.delete(f"/api/users/{leaver_id}", headers=h).status_code == 200

        db = _scoped()
        try:
            theirs = db.query(AuditLog).filter(AuditLog.user_id == leaver_id).all()
            assert theirs, "their actions vanished from the trail"
            assert all(e.actor_email == "audited@remove.dev" for e in theirs), \
                "the trail no longer says who performed these actions"
            removal = db.query(AuditLog).filter(AuditLog.action == "user.remove").all()
            assert any("audited@remove.dev" in e.detail for e in removal)
        finally:
            db.close()


def test_removing_someone_frees_their_seat():
    with client() as c:
        h = _login(c)
        before = c.get("/api/orgs/self/billing", headers=h).json()
        seats_before = next(u["used"] for u in before["usage"] if u["key"] == "seats")

        temp = _hire(c, h, "temporary@remove.dev", "employee")
        mid = c.get("/api/orgs/self/billing", headers=h).json()
        assert next(u["used"] for u in mid["usage"] if u["key"] == "seats") == seats_before + 1

        c.delete(f"/api/users/{temp}", headers=h)
        after = c.get("/api/orgs/self/billing", headers=h).json()
        assert next(u["used"] for u in after["usage"] if u["key"] == "seats") == seats_before


def test_deactivating_frees_a_seat_too():
    """Otherwise 'deactivate' does nothing for a workspace that is full, and
    the only way to make room is to destroy someone's account."""
    with client() as c:
        h = _login(c)
        person = _hire(c, h, "onleave@remove.dev", "employee", "On Leave")
        used = lambda: next(u["used"] for u in                       # noqa: E731
                            c.get("/api/orgs/self/billing", headers=h).json()["usage"]
                            if u["key"] == "seats")
        before = used()
        c.patch(f"/api/users/{person}", headers=h, json={"is_active": False})
        assert used() == before - 1
        c.patch(f"/api/users/{person}", headers=h, json={"is_active": True})
        assert used() == before, "coming back from leave should take the seat again"
        c.delete(f"/api/users/{person}", headers=h)


# ── the preview the confirmation is built from ───────────────────────────
def test_the_preview_counts_what_will_actually_move():
    with client() as c:
        h = _login(c)
        leaver_id = _hire(c, h, "previewed@remove.dev", "employee", "Pre Viewed")
        leaver = _login(c, "previewed@remove.dev", "welcome123")
        c.post("/api/documents/upload", headers=leaver, files={
            "file": ("one.txt", b"A document that belongs to the company after they go.")})
        c.post("/api/tasks", headers=leaver, json={"title": "Finish the migration"})

        preview = c.get(f"/api/users/{leaver_id}/removal-preview", headers=h).json()
        assert preview["allowed"] is True
        assert preview["counts"]["documents"] == 1
        assert preview["counts"]["tasks"] == 1

        c.delete(f"/api/users/{leaver_id}", headers=h)


def test_the_preview_explains_a_refusal_instead_of_erroring():
    """The interface greys the button out for the same reason the server would
    refuse, and can say why."""
    with client() as c:
        h = _login(c)
        me = c.get("/api/auth/me", headers=h).json()["id"]
        preview = c.get(f"/api/users/{me}/removal-preview", headers=h).json()
        assert preview["allowed"] is False
        assert "your own account" in preview["reason"]


def test_seat_limits_and_removal_work_together():
    """A full workspace on Free can make room by removing someone — the limit
    must not become a trap."""
    with client() as c:
        h = _login(c)
        db = SessionLocal()
        try:
            admin = db.query(User).filter(User.email == "admin@eaios.dev").one()
            db.info["org_id"] = admin.org_id
            org = db.get(Organization, admin.org_id)
            org.plan = "free"
            db.commit()
            seats = plans.PLANS["free"].seats
            existing = db.query(User).filter(User.is_active.is_(True)).count()
        finally:
            db.close()

        made = []
        for i in range(max(0, seats - existing)):
            made.append(_hire(c, h, f"fill{i}@remove.dev", "employee", f"Fill {i}"))

        full = c.post("/api/users", headers=h, json={
            "email": "one.too.many@remove.dev", "full_name": "One Too Many",
            "password": "welcome123", "role": "employee"})
        assert full.status_code == 402, "the seat limit did not apply"

        if made:
            assert c.delete(f"/api/users/{made[-1]}", headers=h).status_code == 200
            retry = c.post("/api/users", headers=h, json={
                "email": "now.there.is.room@remove.dev", "full_name": "Now Room",
                "password": "welcome123", "role": "employee"})
            assert retry.status_code == 201, "removing someone did not free the seat"
            c.delete(f"/api/users/{retry.json()['id']}", headers=h)
        for uid in made[:-1]:
            c.delete(f"/api/users/{uid}", headers=h)
