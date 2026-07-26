"""Industry personalisation and the plan limits that make the tiers real.

Two claims are under test here, and they are the two the product is sold on:

1. Picking a field genuinely reconfigures the workspace — specialist agents,
   an automation, a task board, and a corpus that makes the suggested
   questions answerable. A picker that only sets a string on the org row is a
   settings screen wearing a wizard's clothes.
2. The plans are enforced where the action happens, and a refusal carries
   enough for the interface to offer the upgrade instead of a dead end.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models import CustomAgent, Document, Organization, Task, User, Workflow
from app.services import industries, industry_packs, plans


def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _leave_the_workspace_as_we_found_it():
    """Seed the starter corpus, then take it back out again.

    The suite shares one database, so documents this module ingests would
    otherwise show up in the retrieval-quality and knowledge-graph tests as
    unexplained extra sources — and the plan it leaves behind would change what
    every later test is allowed to do.
    """
    yield
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "admin@eaios.dev").one_or_none()
        if user is not None:
            db.info["org_id"] = user.org_id
            industries.remove_samples(db, user)
            org = db.get(Organization, user.org_id)
            if org is not None:
                org.plan = "business"     # what conftest starts every workspace on
                db.commit()
    finally:
        db.close()


def _login(c, email="admin@eaios.dev", pw="admin12345"):
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


def _employee(c, headers, email="colleague@limitco.dev") -> dict:
    """A non-admin in the same workspace. The seeded demo accounts only exist
    when SEED_ON_START is set, which it is not for the suite."""
    c.post("/api/users", headers=headers, json={
        "email": email, "full_name": "Colleague One",
        "password": "welcome123", "role": "employee"})
    r = c.post("/api/auth/login", json={"email": email, "password": "welcome123"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


def _org(db, user_email="admin@eaios.dev") -> Organization:
    user = db.query(User).filter(User.email == user_email).one()
    return db.get(Organization, user.org_id)


def _scoped():
    """A session scoped to the admin's workspace, the way a request is.

    A bare SessionLocal sees every tenant's rows, so asserting on raw counts
    means counting workspaces other test modules created — which is how a
    passing assertion turns into a mystery failure the moment the suite grows.
    """
    db = SessionLocal()
    user = db.query(User).filter(User.email == "admin@eaios.dev").one()
    db.info["org_id"] = user.org_id
    return db


# ── the catalogue is complete ────────────────────────────────────────────
@pytest.mark.parametrize("industry_id", list(industries.INDUSTRIES))
def test_every_industry_ships_a_usable_profile(industry_id):
    profile = industries.INDUSTRIES[industry_id]
    assert len(profile["agents"]) >= 2, "a field with one agent is a label, not a profile"
    assert len(profile["prompts"]) >= 3
    assert profile["workflow"]["nodes"], "the automation must be runnable, not a name"
    assert industry_packs.checklist_for(industry_id), "no first-week route through the product"


@pytest.mark.parametrize("industry_id", list(industries.INDUSTRIES))
def test_every_industry_ships_starter_documents(industry_id):
    """An empty knowledge base answers every suggested question with 'nothing
    found', which reads as a broken product rather than an empty one."""
    docs = industry_packs.for_industry(industry_id)
    assert len(docs) >= 3, f"{industry_id} would open onto an empty workspace"
    for title, text in docs:
        assert title.strip(), "a document with no title cannot be cited"
        tabular = "," in text.lstrip().split("\n", 1)[0] and not text.lstrip().startswith("#")
        if tabular:   # a data file earns its keep in rows, not prose
            assert text.strip().count("\n") >= 5, f"{title} has too few rows to chart"
        else:
            assert len(text) > 600, f"{title} is too thin to answer anything"


def test_starter_documents_are_written_for_their_own_field():
    """The point of the packs is that healthcare reads like healthcare. If the
    same body of text served every profile, the personalisation would be a
    coat of paint."""
    bodies = {k: " ".join(t for _, t in v).lower() for k, v in industry_packs.PACKS.items()}
    assert "infection" in bodies["healthcare"] and "consent" in bodies["healthcare"]
    assert "statement of work" in bodies["it_services"]
    assert "rent review" in bodies["real_estate"] and "break clause" in bodies["real_estate"]
    assert "non-conformance" in bodies["manufacturing"] and "ppe" in bodies["manufacturing"]
    assert "learning outcome" in bodies["education"]
    assert "notice period" in bodies["hr_staffing"] and "carried forward" in bodies["hr_staffing"]
    assert "purchase order" in bodies["finance"]
    assert "lead time" in bodies["retail"]
    # and no two packs are the same text
    assert len(set(bodies.values())) == len(bodies)


def test_the_picker_does_not_leak_prompt_internals():
    """The catalogue is public to any signed-in user; the system prompts that
    make the agents work are not part of it."""
    for entry in industries.catalogue():
        assert "system_prompt" not in str(entry)


# ── applying a profile actually changes the workspace ────────────────────
def test_choosing_a_field_configures_the_whole_workspace():
    with client() as c:
        h = _login(c)
        r = c.post("/api/orgs/self/industry", headers=h, json={"industry": "healthcare"})
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["name"] == "Healthcare & Clinics"
        assert "Protocol Assistant" in body["agents_created"]
        assert body["workflows_created"], "no automation was created"
        assert len(body["documents_created"]) >= 3, "the workspace would open empty"
        assert len(body["tasks_created"]) >= 3, "no route through the first week"
        assert body["prompts"], "nothing to suggest in the chat"

        db = _scoped()
        try:
            assert _org(db).industry == "healthcare"
            assert db.query(CustomAgent).filter(CustomAgent.slug == "protocol-assistant").count() == 1
            assert db.query(Task).filter(Task.source == "onboarding").count() >= 3
            samples = db.query(Document).filter(Document.tags.contains("sample")).all()
            assert samples, "starter documents were not stored"
            # and they are searchable, not just rows
            assert any(d.status == "indexed" and d.chunk_count > 0 for d in samples), \
                "the corpus exists but nothing can be retrieved from it"
        finally:
            db.close()


def test_the_seeded_automation_is_off_until_the_customer_says_so():
    """Something that emails clients the moment you finish signing up is a
    liability, not a feature."""
    with client() as c:
        h = _login(c)
        c.post("/api/orgs/self/industry", headers=h, json={"industry": "legal"})
        db = _scoped()
        try:
            seeded = db.query(Workflow).filter(
                Workflow.name == "New agreement triage").one()
            assert seeded.enabled is False
        finally:
            db.close()


def test_running_the_wizard_twice_refines_rather_than_duplicates():
    with client() as c:
        h = _login(c)
        c.delete("/api/orgs/self/industry/samples", headers=h)   # suite shares one database
        first = c.post("/api/orgs/self/industry", headers=h, json={"industry": "finance"}).json()
        second = c.post("/api/orgs/self/industry", headers=h, json={"industry": "finance"}).json()
        assert first["documents_created"] and not second["documents_created"]
        assert not second["agents_created"] and not second["tasks_created"]
        db = _scoped()
        try:
            assert db.query(Document).filter(Document.tags.contains("sample")).count() == \
                len(first["documents_created"])
        finally:
            db.close()


def test_samples_can_be_declined_at_the_start():
    with client() as c:
        h = _login(c)
        body = c.post("/api/orgs/self/industry", headers=h,
                      json={"industry": "retail", "with_samples": False}).json()
        assert body["documents_created"] == []
        assert body["agents_created"], "declining samples must not skip the rest of the setup"


def test_samples_can_be_removed_in_one_click():
    with client() as c:
        h = _login(c)
        c.post("/api/orgs/self/industry", headers=h, json={"industry": "education"})
        r = c.delete("/api/orgs/self/industry/samples", headers=h)
        assert r.status_code == 200 and r.json()["removed"] >= 3
        db = _scoped()
        try:
            assert db.query(Document).filter(Document.tags.contains("sample")).count() == 0
        finally:
            db.close()


def test_only_an_admin_can_reconfigure_the_workspace():
    """Applying a profile writes shared objects every colleague will see."""
    with client() as c:
        emp = _employee(c, _login(c), "notadmin@limitco.dev")
        assert c.post("/api/orgs/self/industry", headers=emp,
                      json={"industry": "legal"}).status_code == 403


# ── plans ────────────────────────────────────────────────────────────────
def test_plan_ladder_never_takes_something_away_as_you_pay_more():
    ladder = [plans.PLANS[k] for k in plans.ORDER]
    for lower, higher in zip(ladder, ladder[1:]):
        for field in ("documents", "custom_agents", "seats", "automations", "ai_daily_tokens"):
            lo, hi = getattr(lower, field), getattr(higher, field)
            assert hi == plans.UNLIMITED or (lo != plans.UNLIMITED and hi >= lo), \
                f"{higher.name} offers less {field} than {lower.name}"
        for flag in ("connectors", "video", "audit_export"):
            assert getattr(higher, flag) or not getattr(lower, flag), \
                f"{higher.name} loses {flag} compared with {lower.name}"


def test_free_is_a_usable_product_not_a_locked_door():
    free = plans.PLANS["free"]
    assert free.documents >= 10 and free.seats >= 2 and free.custom_agents >= 2, \
        "a free tier that cannot be tried teaches people the product does not work"


def test_a_refusal_carries_the_upgrade_offer():
    err = plans.LimitReached("documents", "out of documents", plans.PLANS["free"], used=25)
    payload = err.as_payload()
    assert payload["limit"] == "documents" and payload["plan"] == "free"
    assert payload["upgrade_to"] == "pro"
    assert "1,000 documents" in payload["upgrade_allows"], \
        "the interface cannot say what upgrading would buy"


def test_the_top_plan_offers_no_further_upgrade():
    err = plans.LimitReached("documents", "nope", plans.PLANS["business"])
    assert err.as_payload()["upgrade_to"] is None


def test_billing_shows_live_usage_against_the_plan():
    with client() as c:
        h = _login(c)
        r = c.get("/api/orgs/self/billing", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["plan"]["id"] in plans.PLANS
        keys = {row["key"] for row in body["usage"]}
        assert {"documents", "custom_agents", "seats", "automations"} <= keys
        assert len(body["plans"]) == 3 and sum(p["current"] for p in body["plans"]) == 1


def test_everyone_can_see_the_plan_but_only_admins_can_change_it():
    """The person who hits a limit is usually not the person who can lift it —
    they still need to understand why they were stopped."""
    with client() as c:
        emp = _employee(c, _login(c), "reader@limitco.dev")
        assert c.get("/api/orgs/self/billing", headers=emp).status_code == 200
        assert c.post("/api/orgs/self/billing/plan", headers=emp,
                      json={"plan": "business"}).status_code == 403


def test_changing_plan_reports_the_move():
    with client() as c:
        h = _login(c)
        r = c.post("/api/orgs/self/billing/plan", headers=h, json={"plan": "pro"})
        assert r.status_code == 200 and r.json()["plan"]["id"] == "pro"
        assert r.json()["usage"], "the caller should see their new headroom immediately"
        c.post("/api/orgs/self/billing/plan", headers=h, json={"plan": "free"})


def test_an_unknown_plan_is_refused():
    with client() as c:
        h = _login(c)
        assert c.post("/api/orgs/self/billing/plan", headers=h,
                      json={"plan": "platinum"}).status_code == 422


# ── the limits bite where the action happens ─────────────────────────────
def test_a_seat_limit_stops_the_hire_and_offers_the_upgrade():
    with client() as c:
        h = _login(c)
        db = SessionLocal()
        try:
            org = _org(db)
            org.plan = "free"
            db.commit()
            seats = plans.PLANS["free"].seats
        finally:
            db.close()

        created, blocked = 0, None
        for i in range(seats + 3):
            r = c.post("/api/users", headers=h, json={
                "email": f"seat{i}@limitco.dev", "full_name": f"Seat {i}",
                "password": "welcome123", "role": "employee"})
            if r.status_code == 402:
                blocked = r
                break
            created += 1

        assert blocked is not None, "the seat limit never applied"
        body = blocked.json()
        assert body["limit"] == "seats"
        assert body["upgrade_to"] == "pro" and body["upgrade_allows"]
        assert "Free" in body["detail"]


def test_an_automation_can_be_built_on_free_but_not_switched_on():
    """The gate is on the switch, not the canvas — you can design the whole
    process and see exactly what you would be buying."""
    with client() as c:
        h = _login(c)
        db = SessionLocal()
        try:
            org = _org(db)
            org.plan = "free"
            db.commit()
        finally:
            db.close()

        draft = {"name": "Nightly digest", "description": "", "trigger": "schedule",
                 "nodes": [{"id": "n1", "type": "trigger", "x": 0, "y": 0, "data": {}}],
                 "edges": [], "enabled": False}
        r = c.post("/api/workflows", headers=h, json=draft)
        assert r.status_code == 201, "building an automation must stay free"

        wf_id = r.json()["id"]
        on = c.put(f"/api/workflows/{wf_id}", headers=h, json={**draft, "enabled": True})
        assert on.status_code == 402
        assert on.json()["limit"] == "automations"
        assert "Free" in on.json()["detail"]


def test_the_same_automation_runs_once_the_plan_allows_it():
    with client() as c:
        h = _login(c)
        draft = {"name": "Weekly digest", "description": "", "trigger": "schedule",
                 "nodes": [{"id": "n1", "type": "trigger", "x": 0, "y": 0, "data": {}}],
                 "edges": [], "enabled": False}
        wf_id = c.post("/api/workflows", headers=h, json=draft).json()["id"]

        db = SessionLocal()
        try:
            _org(db).plan = "pro"
            db.commit()
        finally:
            db.close()

        on = c.put(f"/api/workflows/{wf_id}", headers=h, json={**draft, "enabled": True})
        assert on.status_code == 200 and on.json()["enabled"] is True


def test_a_downgrade_never_deletes_what_the_customer_already_has():
    """Deleting a paying customer's documents because their card expired is
    indefensible. Over the cap means 'no more', not 'lose some'."""
    with client() as c:
        h = _login(c)
        c.post("/api/orgs/self/industry", headers=h, json={"industry": "general"})
        db = _scoped()
        try:
            before = db.query(Document).count()
            org = _org(db)
            org.plan = "free"
            db.commit()
            after = db.query(Document).count()
        finally:
            db.close()
        assert after == before
        assert c.get("/api/documents", headers=h).status_code == 200, \
            "existing documents must stay readable over the cap"


def test_sample_connector_stays_open_on_free_but_real_ones_do_not():
    with client() as c:
        h = _login(c)
        db = SessionLocal()
        try:
            _org(db).plan = "free"
            db.commit()
        finally:
            db.close()

        gated = c.post("/api/connectors/sync", headers=h,
                       json={"provider": "google_drive", "token": "x" * 20})
        assert gated.status_code == 402 and gated.json()["limit"] == "connectors"

        db = SessionLocal()
        try:
            _org(db).plan = "pro"
            db.commit()
        finally:
            db.close()
        allowed = c.post("/api/connectors/sync", headers=h,
                         json={"provider": "google_drive", "token": "x" * 20})
        assert allowed.status_code != 402, "Pro should not be refused on plan grounds"


def test_deleting_a_document_takes_its_entities_out_of_the_graph():
    """Found while seeding starter corpora: the graph kept showing entities
    whose only evidence was a document that had been deleted. An entity with no
    surviving source is worse than no entity in a product that promises every
    answer points somewhere real."""
    from app.services import kgraph

    with client() as c:
        h = _login(c)
        r = c.post("/api/documents/upload", headers=h, files={"file": (
            "orphan_check.txt",
            b"Wexford Analytics signed the Bramblewood agreement. "
            b"Wexford Analytics renewed the Bramblewood agreement in March.")})
        assert r.status_code == 201
        doc_id = r.json()["id"]

        names = [n["name"] for n in c.get("/api/graph", headers=h).json()["nodes"]]
        assert "Wexford Analytics" in names, "nothing was extracted to test with"

        assert c.delete(f"/api/documents/{doc_id}", headers=h).status_code == 204
        after = [n["name"] for n in c.get("/api/graph", headers=h).json()["nodes"]]
        assert "Wexford Analytics" not in after

        db = _scoped()
        try:
            assert kgraph.forget_document(db, doc_id) == 0, "cleanup should be idempotent"
        finally:
            db.close()


def test_an_entity_named_in_other_documents_survives_a_delete():
    """Deleting one contract must not erase a client named in ten others."""
    with client() as c:
        h = _login(c)
        keep = c.post("/api/documents/upload", headers=h, files={"file": (
            "keep_me.txt", b"Thornbury Holdings leads the account. "
                           b"Thornbury Holdings approved the budget.")}).json()["id"]
        drop = c.post("/api/documents/upload", headers=h, files={"file": (
            "drop_me.txt", b"Thornbury Holdings attended the review. "
                           b"Thornbury Holdings requested a change.")}).json()["id"]

        assert c.delete(f"/api/documents/{drop}", headers=h).status_code == 204
        names = [n["name"] for n in c.get("/api/graph", headers=h).json()["nodes"]]
        assert "Thornbury Holdings" in names
        c.delete(f"/api/documents/{keep}", headers=h)


def test_historic_plan_names_still_resolve():
    """`enterprise` predates this module; a workspace on it must not silently
    fall back to Free limits."""
    assert plans.get("enterprise").id == "business"
    assert plans.get(None).id == "free" and plans.get("").id == "free"
