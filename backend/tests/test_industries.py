"""Industry personalisation — the onboarding question and what it configures.

The commercial claim is "answer one question and the workspace is built for
your business", so these tests check that the answer produces real, usable,
tenant-scoped objects rather than a stored label.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import industries


def client() -> TestClient:
    return TestClient(app)


def _signup(c, company, email, pw="welcome123"):
    r = c.post("/api/auth/signup", json={"company_name": company, "full_name": "Owner One",
                                         "email": email, "password": pw})
    assert r.status_code == 201, r.text
    j = r.json()
    return {"Authorization": f"Bearer {j['token']['access_token']}"}, j


# ── the catalogue ────────────────────────────────────────────────────────
def test_catalogue_is_offered_to_a_signed_in_user():
    with client() as c:
        h, _ = _signup(c, "Picker Co", "admin@picker.dev")
        r = c.get("/api/orgs/industries", headers=h)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 8
        for item in items:
            assert item["name"] and item["tagline"] and item["value"]
            assert item["agents"] and item["prompts"]        # every profile earns its place


def test_catalogue_never_leaks_the_agent_prompts():
    """System prompts are product IP; the picker only advertises capability."""
    with client() as c:
        h, _ = _signup(c, "Leak Co", "admin@leakco.dev")
        body = c.get("/api/orgs/industries", headers=h).text
        assert "system_prompt" not in body
        assert "You analyse statements of work" not in body


def test_a_new_workspace_starts_with_no_industry():
    with client() as c:
        _, j = _signup(c, "Fresh Co", "admin@freshco.dev")
        assert j["org"]["industry"] == ""      # the wizard uses this to decide to ask


# ── applying a profile ───────────────────────────────────────────────────
def test_choosing_an_industry_creates_real_agents_and_an_automation():
    with client() as c:
        h, _ = _signup(c, "Clinic Co", "admin@clinicco.dev")
        r = c.post("/api/orgs/self/industry", headers=h, json={"industry": "healthcare"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["name"] == "Healthcare & Clinics"
        assert len(out["agents_created"]) == 2
        assert len(out["workflows_created"]) == 1

        # the agents are real, routable custom agents — not a stored label
        agents = c.get("/api/studio/agents", headers=h).json()
        names = [a["name"] for a in agents]
        assert "Protocol Assistant" in names and "Compliance Assistant" in names

        # the automation exists and is deliberately switched OFF until enabled
        flows = c.get("/api/workflows", headers=h).json()
        assert any(w["name"] == "Policy change review" for w in flows)
        assert all(not w["enabled"] for w in flows if w["name"] == "Policy change review")


def test_the_choice_is_remembered_across_sessions():
    with client() as c:
        _signup(c, "Legal Co", "admin@legalco.dev")
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"email": "admin@legalco.dev", "password": "welcome123"}
        ).json()["token"]["access_token"]}
        c.post("/api/orgs/self/industry", headers=h, json={"industry": "legal"})

        again = c.post("/api/auth/login", json={"email": "admin@legalco.dev", "password": "welcome123"})
        assert again.json()["org"]["industry"] == "legal"   # never asked twice


def test_applying_twice_does_not_duplicate_anything():
    with client() as c:
        h, _ = _signup(c, "Twice Co", "admin@twiceco.dev")
        c.post("/api/orgs/self/industry", headers=h, json={"industry": "finance"})
        second = c.post("/api/orgs/self/industry", headers=h, json={"industry": "finance"}).json()
        assert second["agents_created"] == []               # idempotent
        agents = [a["name"] for a in c.get("/api/studio/agents", headers=h).json()]
        assert agents.count("Invoice Auditor") == 1


def test_an_unknown_industry_is_rejected():
    with client() as c:
        h, _ = _signup(c, "Unknown Co", "admin@unknownco.dev")
        assert c.post("/api/orgs/self/industry", headers=h,
                      json={"industry": "not-a-real-field"}).status_code == 422


# ── access control and isolation ─────────────────────────────────────────
def test_only_an_admin_can_configure_the_workspace():
    with client() as c:
        h, _ = _signup(c, "Staffed Ind Co", "admin@staffedind.dev")
        c.post("/api/users", headers=h, json={"email": "emp@staffedind.dev", "full_name": "Emp Loyee",
                                              "password": "welcome123", "role": "employee"})
        he = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"email": "emp@staffedind.dev", "password": "welcome123"}
        ).json()["token"]["access_token"]}
        assert c.post("/api/orgs/self/industry", headers=he,
                      json={"industry": "legal"}).status_code == 403


def test_generated_agents_belong_only_to_the_workspace_that_chose_them():
    """The profile writes tenant data, so isolation must still hold."""
    with client() as c:
        ha, _ = _signup(c, "Alpha Ind", "admin@alphaind.dev")
        hb, _ = _signup(c, "Beta Ind", "admin@betaind.dev")
        c.post("/api/orgs/self/industry", headers=ha, json={"industry": "manufacturing"})

        b_agents = [a["name"] for a in c.get("/api/studio/agents", headers=hb).json()]
        assert "SOP Guide" not in b_agents
        b_flows = [w["name"] for w in c.get("/api/workflows", headers=hb).json()]
        assert "Quality record intake" not in b_flows


def test_two_workspaces_can_hold_the_same_agent_slug():
    """Slugs are unique per workspace, not globally — otherwise the first
    customer to pick a profile would block every later one."""
    with client() as c:
        ha, _ = _signup(c, "Same Slug A", "admin@slug-a.dev")
        hb, _ = _signup(c, "Same Slug B", "admin@slug-b.dev")
        assert c.post("/api/orgs/self/industry", headers=ha, json={"industry": "legal"}).status_code == 200
        assert c.post("/api/orgs/self/industry", headers=hb, json={"industry": "legal"}).status_code == 200
        for h in (ha, hb):
            assert "Clause Finder" in [a["name"] for a in c.get("/api/studio/agents", headers=h).json()]


# ── profile quality ──────────────────────────────────────────────────────
@pytest.mark.parametrize("industry_id", list(industries.INDUSTRIES))
def test_every_profile_is_complete_and_specific(industry_id):
    p = industries.INDUSTRIES[industry_id]
    assert p["agents"], f"{industry_id} has no agents"
    assert len(p["prompts"]) >= 3
    assert p["workflow"]["nodes"] and p["workflow"]["edges"]
    for agent in p["agents"]:
        # A prompt short enough to be generic is not worth paying for.
        assert len(agent["system_prompt"]) > 200, f"{agent['slug']} prompt is too thin"
        assert agent["slug"].islower() and " " not in agent["slug"]
