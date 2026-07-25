"""Workspace lifecycle — suspend, delete, and who is allowed to do it.

Deleting a workspace is the most destructive action in the product, so these
tests pin the guards as hard as the behaviour: who can call it, what has to be
typed to confirm it, and that it removes the tenant's rows *and nothing else*.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _signup(c, company, email, name="Owner One", pw="welcome123"):
    r = c.post("/api/auth/signup", json={"company_name": company, "full_name": name,
                                         "email": email, "password": pw})
    assert r.status_code == 201, r.text
    j = r.json()
    return {"Authorization": f"Bearer {j['token']['access_token']}"}, j


@pytest.fixture
def owner_env(monkeypatch, request):
    """Make a unique email the platform owner for the duration of one test.
    Unique because the whole module shares one database."""
    email = f"boss_{abs(hash(request.node.name)) % 10**8}@vendor.dev"
    monkeypatch.setattr(settings, "PLATFORM_OWNER_EMAILS", email)
    return email


def _owner_headers(c, email, pw="welcome123"):
    tok = c.post("/api/auth/login", json={"email": email, "password": pw}).json()["token"]["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ── access control ───────────────────────────────────────────────────────
def test_console_is_disabled_when_no_owner_is_configured(monkeypatch):
    """Default config = no platform owner = console unreachable, even for an
    admin. A leaked demo login must not be able to list or delete workspaces."""
    monkeypatch.setattr(settings, "PLATFORM_OWNER_EMAILS", "")
    with client() as c:
        h, _ = _signup(c, "Nobody Ltd", "admin@nobody.dev")
        assert c.get("/api/orgs", headers=h).status_code == 403


def test_ordinary_company_admin_cannot_see_or_touch_other_workspaces(owner_env):
    with client() as c:
        ha, _ = _signup(c, "Alpha Inc", "admin@alpha-ws.dev")
        _, jb = _signup(c, "Beta LLC", "admin@beta-ws.dev")
        b_org = jb["org"]["id"]

        assert c.get("/api/orgs", headers=ha).status_code == 403
        assert c.patch(f"/api/orgs/{b_org}", headers=ha, json={"status": "suspended"}).status_code == 403
        assert c.request("DELETE", f"/api/orgs/{b_org}", headers=ha,
                         json={"confirm": "Beta LLC"}).status_code == 403
        # Beta survived
        assert c.post("/api/auth/login", json={"email": "admin@beta-ws.dev",
                                               "password": "welcome123"}).status_code == 200


def test_platform_owner_sees_every_workspace_with_counts(owner_env):
    with client() as c:
        _signup(c, "Vendor HQ", owner_env)          # the owner's own workspace
        _signup(c, "Customer One", "a@cust1.dev")
        ho = _owner_headers(c, owner_env)

        r = c.get("/api/orgs", headers=ho)
        assert r.status_code == 200
        names = [o["name"] for o in r.json()]
        assert "Vendor HQ" in names and "Customer One" in names
        cust = next(o for o in r.json() if o["name"] == "Customer One")
        assert cust["stats"]["users"] == 1 and cust["status"] == "active"


# ── suspend ──────────────────────────────────────────────────────────────
def test_suspend_blocks_login_and_reactivate_restores_it(owner_env):
    with client() as c:
        _signup(c, "Vendor HQ", owner_env)
        _, jc = _signup(c, "Trial Co", "user@trial.dev")
        ho = _owner_headers(c, owner_env)

        assert c.patch(f"/api/orgs/{jc['org']['id']}", headers=ho,
                       json={"status": "suspended"}).json()["status"] == "suspended"
        blocked = c.post("/api/auth/login", json={"email": "user@trial.dev", "password": "welcome123"})
        assert blocked.status_code == 403 and "suspended" in blocked.json()["detail"].lower()

        c.patch(f"/api/orgs/{jc['org']['id']}", headers=ho, json={"status": "active"})
        assert c.post("/api/auth/login", json={"email": "user@trial.dev",
                                               "password": "welcome123"}).status_code == 200


# ── delete ───────────────────────────────────────────────────────────────
def test_delete_requires_typing_the_exact_workspace_name(owner_env):
    with client() as c:
        _signup(c, "Vendor HQ", owner_env)
        _, jd = _signup(c, "Typo Co", "user@typo.dev")
        ho = _owner_headers(c, owner_env)

        bad = c.request("DELETE", f"/api/orgs/{jd['org']['id']}", headers=ho,
                        json={"confirm": "typo co"})       # wrong case
        assert bad.status_code == 400
        assert c.post("/api/auth/login", json={"email": "user@typo.dev",
                                               "password": "welcome123"}).status_code == 200


def test_owner_delete_removes_the_workspace_and_only_its_data(owner_env):
    with client() as c:
        _signup(c, "Vendor HQ", owner_env)
        hk, jk = _signup(c, "Keep Co", "admin@keep.dev")
        hd, jd = _signup(c, "Doomed Co", "admin@doomed.dev")
        ho = _owner_headers(c, owner_env)

        # Give both workspaces content.
        for h, title in ((hk, "keep note"), (hd, "doomed note")):
            c.post("/api/tasks", headers=h, json={"title": title})
            c.post("/api/documents/upload", headers=h,
                   files={"file": ("f.txt", io.BytesIO(b"payload for this workspace"), "text/plain")})
            c.post("/api/chat", headers=h, json={"message": "hello"})

        r = c.request("DELETE", f"/api/orgs/{jd['org']['id']}", headers=ho,
                      json={"confirm": "Doomed Co"})
        assert r.status_code == 200, r.text
        assert r.json()["rows"]["users"] == 1

        # Gone: workspace, its login, its rows.
        assert c.post("/api/auth/login", json={"email": "admin@doomed.dev",
                                               "password": "welcome123"}).status_code == 401
        assert jd["org"]["id"] not in [o["id"] for o in c.get("/api/orgs", headers=ho).json()]

        # Untouched: the other workspace still has all of its data.
        assert c.post("/api/auth/login", json={"email": "admin@keep.dev",
                                               "password": "welcome123"}).status_code == 200
        assert [t["title"] for t in c.get("/api/tasks", headers=hk).json()] == ["keep note"]
        assert len(c.get("/api/documents", headers=hk).json()) == 1
        assert len(c.get("/api/chat/conversations", headers=hk).json()) >= 1


def test_company_admin_can_delete_their_own_workspace(owner_env):
    with client() as c:
        h, j = _signup(c, "Selfclose Ltd", "admin@selfclose.dev")
        c.post("/api/tasks", headers=h, json={"title": "will vanish"})

        wrong = c.request("DELETE", "/api/orgs/self/workspace", headers=h,
                          json={"confirm": "something else"})
        assert wrong.status_code == 400

        ok = c.request("DELETE", "/api/orgs/self/workspace", headers=h,
                       json={"confirm": "Selfclose Ltd"})
        assert ok.status_code == 200, ok.text
        assert c.post("/api/auth/login", json={"email": "admin@selfclose.dev",
                                               "password": "welcome123"}).status_code == 401


def test_non_admin_cannot_delete_their_workspace(owner_env):
    with client() as c:
        h, _ = _signup(c, "Staffed Co", "admin@staffed.dev")
        c.post("/api/users", headers=h, json={"email": "emp@staffed.dev", "full_name": "Emp Loyee",
                                              "password": "welcome123", "role": "employee"})
        he = _owner_headers(c, "emp@staffed.dev")
        assert c.request("DELETE", "/api/orgs/self/workspace", headers=he,
                         json={"confirm": "Staffed Co"}).status_code == 403


def test_shared_demo_workspace_cannot_be_deleted():
    """The demo workspace backs the public login on the live site."""
    with client() as c:
        tok = c.post("/api/auth/login", json={"email": "admin@eaios.dev",
                                              "password": "admin12345"}).json()["token"]["access_token"]
        r = c.request("DELETE", "/api/orgs/self/workspace",
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"confirm": "EAIOS Demo Workspace"})
        assert r.status_code == 400 and "demo" in r.json()["detail"].lower()
