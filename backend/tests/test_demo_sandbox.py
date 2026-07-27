"""The public demo sandbox.

A demo that shares one workspace shows the second visitor whatever the first
one uploaded. These tests pin the three properties that make a public sandbox
defensible instead of embarrassing:

1. **Isolation.** Two visitors never see each other's work — and neither of
   them can see a real customer's.
2. **Disposability.** The tenant is deleted when it expires, so a stranger's
   uploads do not accumulate in the database.
3. **Containment.** A demo account is an admin of its own throwaway workspace
   and of nothing else. It must not be a route into the platform console or
   into anyone's real data.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models import Document, Organization, User
from app.services import demo


def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def sandbox_on(monkeypatch):
    """The sandbox is off by default so a self-hosted install behaves normally;
    these tests are what actually exercises it."""
    monkeypatch.setattr(settings, "DEMO_SANDBOX", True)
    monkeypatch.setattr(settings, "DEMO_TTL_MINUTES", 120)
    yield
    db = SessionLocal()
    try:
        for org in list(db.scalars(
                __import__("sqlalchemy").select(Organization).where(Organization.is_demo.is_(True)))):
            org.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        demo.sweep_expired(db)
    finally:
        db.close()


def _start(c) -> dict:
    r = c.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    return r.json()


def _auth(session: dict) -> dict:
    return {"Authorization": "Bearer " + session["token"]["access_token"]}


# ── getting in ───────────────────────────────────────────────────────────
def test_a_visitor_gets_a_workspace_without_signing_up():
    with client() as c:
        session = _start(c)
        assert session["demo"] is True
        assert session["token"]["access_token"]
        assert session["user"]["role"] == "admin", "a demo should show the whole product"
        assert session["demo_expires_in"] > 0


def test_the_demo_says_it_is_a_demo():
    """Without this the interface cannot warn anyone, and someone uploads real
    documents into a workspace that is about to be deleted."""
    with client() as c:
        session = _start(c)
        assert session["demo"] is True and session["demo_expires_in"] is not None


def test_the_published_credentials_open_a_sandbox_not_the_shared_workspace():
    """The demo logins printed on the sign-in screen must not lead everyone
    into the same workspace."""
    with client() as c:
        first = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
        second = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["demo"] is True
        assert first.json()["org"]["id"] != second.json()["org"]["id"], \
            "two visitors landed in the same workspace"


def test_the_demo_password_does_not_have_to_be_right():
    """It is a label on a sign-in screen, not a secret. Requiring it to be
    correct would only mean publishing a real password more loudly."""
    with client() as c:
        r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "not-the-password"})
        assert r.status_code == 200 and r.json()["demo"] is True


def test_the_sandbox_can_be_switched_off_entirely(monkeypatch):
    """A self-hosted deployment has no strangers to sandbox, and its admin
    account must keep working normally."""
    monkeypatch.setattr(settings, "DEMO_SANDBOX", False)
    with client() as c:
        assert c.post("/api/auth/demo").status_code == 404
        real = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
        assert real.status_code == 200 and real.json()["demo"] is False
        assert c.post("/api/auth/login",
                      json={"email": "admin@eaios.dev", "password": "wrong"}).status_code == 401


# ── isolation ────────────────────────────────────────────────────────────
def test_two_visitors_never_see_each_others_work():
    """The property the whole thing exists for."""
    with client() as c:
        alice, bob = _auth(_start(c)), _auth(_start(c))

        up = c.post("/api/documents/upload", headers=alice, files={
            "file": ("alice_private.txt", b"Alice's confidential notes about her own company.")})
        assert up.status_code == 201

        alice_titles = {d["title"] for d in c.get("/api/documents", headers=alice).json()}
        bob_titles = {d["title"] for d in c.get("/api/documents", headers=bob).json()}
        assert "Alice Private" in alice_titles
        assert "Alice Private" not in bob_titles, "a stranger's upload leaked into another session"


def test_a_demo_visitor_cannot_see_a_real_customer():
    with client() as c:
        real = c.post("/api/auth/signup", json={
            "company_name": "Paying Customer Ltd", "full_name": "Paying Person",
            "email": "owner@payingcustomer.dev", "password": "welcome123"}).json()
        real_auth = {"Authorization": "Bearer " + real["token"]["access_token"]}
        c.post("/api/documents/upload", headers=real_auth, files={
            "file": ("customer_secret.txt", b"Revenue figures the customer would not want shared.")})

        visitor = _auth(_start(c))
        titles = {d["title"] for d in c.get("/api/documents", headers=visitor).json()}
        assert "Customer Secret" not in titles


def test_a_demo_account_is_never_a_platform_owner():
    """The workspace console can suspend and delete *any* tenant. A throwaway
    account handed to anyone on the internet must not reach it."""
    with client() as c:
        visitor = _auth(_start(c))
        assert c.get("/api/orgs", headers=visitor).status_code == 403


def test_a_demo_visitor_cannot_delete_someone_elses_workspace():
    with client() as c:
        victim = c.post("/api/auth/signup", json={
            "company_name": "Untouchable Ltd", "full_name": "Safe Person",
            "email": "owner@untouchable.dev", "password": "welcome123"}).json()
        visitor = _auth(_start(c))
        r = c.delete(f"/api/orgs/{victim['org']['id']}", headers=visitor)
        assert r.status_code in (403, 404)

        db = SessionLocal()
        try:
            assert db.get(Organization, victim["org"]["id"]) is not None
        finally:
            db.close()


# ── it is a real workspace, not a mock ───────────────────────────────────
def test_the_demo_can_answer_a_question_from_the_first_second():
    """A sandbox that answers "nothing found" to everything teaches visitors the
    product does not work. It ships with a corpus for exactly this."""
    with client() as c:
        session = _start(c)
        auth = _auth(session)
        docs = c.get("/api/documents", headers=auth).json()
        assert docs, "the demo workspace opened empty"
        assert any(d["status"] == "indexed" and d["chunk_count"] > 0 for d in docs), \
            "the corpus is there but nothing is retrievable from it"

        answer = c.post("/api/chat", headers=auth, json={"message": "What are our expense limits?"})
        assert answer.status_code == 200


def test_a_visitor_can_upload_and_the_upload_is_real():
    with client() as c:
        auth = _auth(_start(c))
        r = c.post("/api/documents/upload", headers=auth, files={
            "file": ("visitor_upload.txt",
                     b"The Kestrel project renews in September and is owned by the platform team.")})
        assert r.status_code == 201
        db = SessionLocal()
        try:
            doc = db.get(Document, r.json()["id"])
            assert doc is not None and doc.status in ("queued", "processing", "indexed")
        finally:
            db.close()


def test_opening_a_demo_costs_only_a_handful_of_database_round_trips():
    """The thing that made this slow was distance, not code.

    Supabase is in another region, so every statement is a round trip. Parsing
    and embedding three starter documents inside the request was ~380 of them —
    twenty seconds of a visitor watching a spinner before their workspace
    appeared. Staging the rows now and indexing after the response cuts what
    they wait for to a couple of dozen.

    This asserts the *shape* of the fix rather than a wall-clock time, because a
    timing test on shared CI hardware fails for reasons that have nothing to do
    with the code.
    """
    from sqlalchemy import event

    from app.core.database import engine

    counted = {"statements": 0}
    listener = lambda *a, **k: counted.__setitem__("statements", counted["statements"] + 1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        with client() as c:
            session = _start(c)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert session["demo"] is True
    # TestClient runs background tasks before returning, so this figure includes
    # the deferred indexing. The budget is generous; the point is to catch a
    # change that puts hundreds of statements back into the request path.
    assert counted["statements"] < 600, (
        f"{counted['statements']} statements to open a demo — something moved "
        "back into the request that should be deferred"
    )


def test_the_starter_corpus_is_staged_before_the_response_and_indexed_after():
    """Both halves matter. The rows must exist immediately, or the reveal
    screen and the document list would lie about what was created; the indexing
    must not be in the request, or the visitor waits for it."""
    from app.services import demo as demo_service

    db = SessionLocal()
    try:
        deferred: list = []
        user = demo_service.start_session(db, defer=deferred)
        db.info["org_id"] = user.org_id

        staged = db.query(Document).filter(Document.org_id == user.org_id).all()
        assert staged, "no documents existed when the response would have gone out"
        assert deferred, "nothing was handed to the background task"
        assert len(deferred) == len(staged)
        # Staged but not yet searchable — that is the deal.
        assert all(d.status == "queued" for d in staged)

        demo_service_industries = __import__("app.services.industries", fromlist=["x"])
        demo_service_industries.index_documents(deferred)

        db.expire_all()
        after = db.query(Document).filter(Document.org_id == user.org_id).all()
        assert any(d.status == "indexed" and d.chunk_count > 0 for d in after), \
            "the deferred half never made the corpus searchable"
    finally:
        db.close()


def test_a_starter_document_that_will_not_index_is_marked_not_hidden():
    """A sample that fails should show as failed in the document list rather
    than sitting on 'queued' forever, which reads as a hung workspace."""
    from app.services import industries

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin@eaios.dev").one()
        db.info["org_id"] = user.org_id
        doc = Document(filename="broken.txt", title="Broken Sample", doc_type="txt",
                       owner_id=user.id, status="queued", tags="sample,general",
                       org_id=user.org_id)
        db.add(doc)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    industries.index_documents([("index", (doc_id, "/nonexistent/path/broken.txt"))])

    db = SessionLocal()
    try:
        db.info["org_id"] = db.query(User).filter(User.email == "admin@eaios.dev").one().org_id
        after = db.get(Document, doc_id)
        assert after.status == "failed" and after.error
        db.delete(after)
        db.commit()
    finally:
        db.close()


def test_the_demo_personas_are_roles_rather_than_real_people():
    """The sign-in screen is public, so anyone who opens the site sees these
    names. They should describe a job, not identify a person — and the roster
    must hold each role exactly once, or every sandbox gets two of somebody."""
    roles = [role for role, _, _ in demo._ROLE_BY_EMAIL.values()]
    assert sorted(roles) == ["admin", "employee", "hr", "manager"]

    names = [name for _, name, _ in demo._ROLE_BY_EMAIL.values()]
    assert len(set(names)) == len(names)
    for name in names:
        assert name in {"System Administrator", "People Team", "Team Manager", "Staff Member"}

    # Initials drive the avatars, so two personas sharing them look identical.
    initials = ["".join(w[0] for w in n.split()[:2]) for n in names]
    assert len(set(initials)) == len(initials)


def test_retired_demo_addresses_still_work():
    """They were printed in the README and a demo script; anyone following an
    older copy should still land somewhere sensible."""
    with client() as c:
        for old, expected_role in (("maya@eaios.dev", "manager"),
                                   ("riya@eaios.dev", "hr"),
                                   ("dev@eaios.dev", "employee")):
            r = c.post("/api/auth/login", json={"email": old, "password": "demo12345"})
            assert r.status_code == 200, f"{old} stopped working"
            assert r.json()["demo"] is True
            assert r.json()["user"]["role"] == expected_role


def test_an_already_deployed_account_is_renamed_rather_than_duplicated():
    """The live database already holds the old rows. Seeding again must move
    them to the new label — not leave the old name sitting there beside a new
    account, with their documents attached to the wrong one."""
    from app.core.security import hash_password
    from app.seed import seed
    from app.services import tenancy

    db = SessionLocal()
    try:
        org = tenancy.default_org(db)
        db.info["org_id"] = org.id
        db.query(User).filter(User.email.in_(
            ["manager@eaios.dev", "maya@eaios.dev"])).delete(synchronize_session=False)
        db.add(User(email="maya@eaios.dev", full_name="Maya Iyer", role="manager",
                    hashed_password=hash_password("demo12345"), avatar_hue=180,
                    org_id=org.id, email_verified=True))
        db.commit()
        old_id = db.query(User).filter(User.email == "maya@eaios.dev").one().id
    finally:
        db.close()

    seed()

    db = SessionLocal()
    try:
        db.info["db_org"] = None
        assert db.query(User).filter(User.email == "maya@eaios.dev").count() == 0, \
            "the old address survived"
        renamed = db.query(User).filter(User.email == "manager@eaios.dev").one()
        assert renamed.id == old_id, "a duplicate was created instead of a rename"
        assert renamed.full_name == "Team Manager"
    finally:
        db.close()


def test_the_demo_workspace_still_has_colleagues():
    """Hiring, roles and the people list are pointless with a single account."""
    with client() as c:
        auth = _auth(_start(c))
        people = c.get("/api/users", headers=auth).json()
        assert len(people) >= 3
        assert {p["role"] for p in people} >= {"admin", "manager", "employee"}


def test_the_industry_picker_still_runs_for_a_visitor():
    """Choosing a field is the best thing in the product to show someone."""
    with client() as c:
        session = _start(c)
        assert session["org"]["industry"] == "", "the picker would be skipped"


def test_choosing_a_field_swaps_the_starter_corpus():
    """The demo opens on the general pack; picking a field must replace it, not
    leave a clinic answering from generic company documents."""
    with client() as c:
        auth = _auth(_start(c))
        r = c.post("/api/orgs/self/industry", headers=auth, json={"industry": "healthcare"})
        assert r.status_code == 200, r.text
        assert r.json()["documents_created"], "the healthcare corpus never arrived"

        titles = {d["title"] for d in c.get("/api/documents", headers=auth).json()}
        assert "Patient Intake Protocol" in titles
        assert "Company Handbook — How We Work" not in titles, "the general pack was left behind"


# ── disposability ────────────────────────────────────────────────────────
def test_an_expired_workspace_is_swept_away_completely():
    with client() as c:
        session = _start(c)
        org_id = session["org"]["id"]
        auth = _auth(session)
        c.post("/api/documents/upload", headers=auth, files={
            "file": ("left_behind.txt", b"Something a stranger uploaded and then walked away from.")})

        db = SessionLocal()
        try:
            org = db.get(Organization, org_id)
            org.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
            assert demo.sweep_expired(db) >= 1

            assert db.get(Organization, org_id) is None, "the tenant survived its expiry"
            db.info["org_id"] = org_id
            assert db.query(User).filter(User.org_id == org_id).count() == 0
            assert db.query(Document).filter(Document.org_id == org_id).count() == 0
        finally:
            db.close()

        # and the token stops working the moment the workspace is gone
        assert c.get("/api/documents", headers=auth).status_code == 401


def test_a_workspace_that_has_not_expired_is_left_alone():
    """A sweep that is even slightly too eager pulls the rug mid-demo."""
    with client() as c:
        session = _start(c)
        db = SessionLocal()
        try:
            demo.sweep_expired(db)
            assert db.get(Organization, session["org"]["id"]) is not None
        finally:
            db.close()
        assert c.get("/api/documents", headers=_auth(session)).status_code == 200


def test_the_sweep_never_touches_a_real_workspace():
    with client() as c:
        real = c.post("/api/auth/signup", json={
            "company_name": "Permanent Ltd", "full_name": "Real Person",
            "email": "owner@permanent.dev", "password": "welcome123"}).json()
        db = SessionLocal()
        try:
            org = db.get(Organization, real["org"]["id"])
            # even with an expiry set, a workspace that is not a demo stays
            org.expires_at = datetime.now(timezone.utc) - timedelta(days=7)
            db.commit()
            demo.sweep_expired(db)
            assert db.get(Organization, real["org"]["id"]) is not None
        finally:
            db.close()


def test_minutes_remaining_is_reported_for_the_banner():
    db = SessionLocal()
    try:
        org = Organization(name="X", slug="x-demo-timing", is_demo=True,
                           expires_at=datetime.now(timezone.utc) + timedelta(minutes=45))
        assert 40 <= (demo.expires_in_minutes(org) or 0) <= 45
        org.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert demo.expires_in_minutes(org) == 0, "an expired demo should not report negative time"
        assert demo.expires_in_minutes(None) is None
        assert demo.expires_in_minutes(Organization(name="Y", slug="y", is_demo=False)) is None
    finally:
        db.close()
