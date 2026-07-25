"""Multi-tenant SaaS isolation — the security-critical guarantee that one
company can never see another company's data. If any of these fail, that's a
customer data leak."""
import io

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _signup(c, company, email, name="Owner", pw="welcome123"):
    r = c.post("/api/auth/signup", json={"company_name": company, "full_name": name,
                                         "email": email, "password": pw})
    assert r.status_code == 201, r.text
    j = r.json()
    return {"Authorization": f"Bearer {j['token']['access_token']}"}, j


def test_signup_creates_isolated_org_with_admin():
    with client() as c:
        h, j = _signup(c, "Acme Corp", "owner@acme.dev")
        assert j["user"]["role"] == "admin"
        assert j["org"]["name"] == "Acme Corp" and j["org"]["slug"] == "acme-corp"
        # a second company with the same name gets a distinct slug
        _, j2 = _signup(c, "Acme Corp", "owner2@acme.dev")
        assert j2["org"]["slug"] != j["org"]["slug"]


def test_two_companies_cannot_see_each_others_data():
    with client() as c:
        ha, ja = _signup(c, "Alpha Inc", "admin@alpha.dev")
        hb, jb = _signup(c, "Beta LLC", "admin@beta.dev")

        # ── users: each admin sees only their own org's users ──
        alpha_users = c.get("/api/users", headers=ha).json()
        beta_users = c.get("/api/users", headers=hb).json()
        assert [u["email"] for u in alpha_users] == ["admin@alpha.dev"]
        assert [u["email"] for u in beta_users] == ["admin@beta.dev"]

        # Alpha hires an employee; Beta must not see them
        c.post("/api/users", headers=ha, json={"email": "e@alpha.dev", "full_name": "Alpha Emp",
                                               "password": "welcome123", "role": "employee"})
        assert any(u["email"] == "e@alpha.dev" for u in c.get("/api/users", headers=ha).json())
        assert not any(u["email"] == "e@alpha.dev" for u in c.get("/api/users", headers=hb).json())

        # ── documents ──
        up = c.post("/api/documents/upload", headers=ha,
                    files={"file": ("alpha_secret.txt", io.BytesIO(b"Alpha confidential: Q4 revenue 5cr."), "text/plain")})
        assert up.status_code == 201
        assert any(d["title"] == "Alpha Secret" for d in c.get("/api/documents", headers=ha).json())
        assert c.get("/api/documents", headers=hb).json() == []   # Beta sees no Alpha docs

        # ── tasks ──
        c.post("/api/tasks", headers=ha, json={"title": "Alpha-only task"})
        assert any(t["title"] == "Alpha-only task" for t in c.get("/api/tasks", headers=ha).json())
        assert c.get("/api/tasks", headers=hb).json() == []

        # ── chat / conversations ──
        c.post("/api/chat", headers=ha, json={"message": "Remember Alpha's secret project name is Falcon"})
        assert len(c.get("/api/chat/conversations", headers=ha).json()) >= 1
        assert c.get("/api/chat/conversations", headers=hb).json() == []

        # ── global search: Beta searching Alpha's keyword finds nothing ──
        sb = c.get("/api/search", headers=hb, params={"q": "confidential"}).json()
        assert sb["documents"] == [] and sb["passages"] == [] and sb["messages"] == []

        # ── HR/admin cannot cross-edit: Beta admin can't touch Alpha's employee ──
        alpha_emp_id = next(u["id"] for u in c.get("/api/users", headers=ha).json() if u["email"] == "e@alpha.dev")
        assert c.patch(f"/api/users/{alpha_emp_id}", headers=hb, json={"role": "manager"}).status_code == 404


def test_rag_is_tenant_scoped():
    """Company B asking about Company A's uploaded content must not retrieve it."""
    with client() as c:
        ha, _ = _signup(c, "Gamma Co", "admin@gamma.dev")
        hb, _ = _signup(c, "Delta Co", "admin@delta.dev")
        c.post("/api/documents/upload", headers=ha,
               files={"file": ("gamma_policy.txt",
                               io.BytesIO(b"Gamma leave policy: employees get 27 vacation days per year."), "text/plain")})
        # Gamma's admin can retrieve it
        ga = c.get("/api/search", headers=ha, params={"q": "vacation days"}).json()
        assert ga["documents"] or ga["passages"]
        # Delta's admin retrieves nothing about Gamma's policy
        db_ = c.get("/api/search", headers=hb, params={"q": "vacation days"}).json()
        assert db_["documents"] == [] and db_["passages"] == []


def test_sql_agent_cannot_read_across_workspaces():
    """The SQL agent runs raw SQL, which bypasses the ORM tenant filter — so it
    has its own guard. Company B must not be able to count or read Company A's
    rows, even by asking the SQL agent directly."""
    with client() as c:
        ha, _ = _signup(c, "Sigma Inc", "admin@sigma.dev")
        hb, _ = _signup(c, "Omega LLC", "admin@omega.dev")
        # Sigma grows to 3 users; Omega stays at 1.
        for e in ("a@sigma.dev", "b@sigma.dev"):
            c.post("/api/users", headers=ha, json={"email": e, "full_name": "Sigma P",
                                                   "password": "welcome123", "role": "employee"})

        # Omega asks "how many users" → must count ONLY its own workspace (1).
        r = c.post("/api/agents/sql", headers=hb, json={"question": "how many users are there"})
        assert r.status_code == 200
        total = r.json()["rows"][0][0]
        assert total == 1, f"SQL agent leaked cross-org user count: {total}"

        # Omega lists users → no Sigma email may appear in any cell.
        r2 = c.post("/api/agents/sql", headers=hb, json={"question": "show me the most recent users"})
        cells = " ".join(str(v) for row in r2.json().get("rows", []) for v in row)
        assert "sigma.dev" not in cells, f"SQL agent leaked Sigma rows: {cells}"


def test_sql_guard_rewrites_tenant_tables_and_rejects_unscopable():
    """Unit-level proof of the raw-SQL guard: tenant tables get an injected
    org filter; the tenant registry and un-scopable shapes are refused."""
    import pytest

    from app.agents.sql_agent import SQLAgent, _GuardReject
    from app.core.database import SessionLocal

    with client():  # ensure tables exist (app startup)
        db = SessionLocal()
        db.info["org_id"] = "org_unit_test"
        agent = SQLAgent(db, None)  # user unused by the scope logic
        try:
            scoped, params = agent._tenant_scope("SELECT COUNT(*) AS total FROM users")
            assert "org_id = :org" in scoped and params == {"org": "org_unit_test"}
            with pytest.raises(_GuardReject):        # tenant registry off-limits
                agent._tenant_scope("SELECT * FROM organizations")
            with pytest.raises(_GuardReject):        # alias → can't inject safely
                agent._tenant_scope("SELECT * FROM users u WHERE u.role = 'admin'")
            # no org context → passthrough (system / single-tenant paths)
            db.info.pop("org_id")
            passthrough, p2 = agent._tenant_scope("SELECT * FROM users")
            assert passthrough == "SELECT * FROM users" and p2 == {}
        finally:
            db.close()


def test_demo_login_still_works_in_default_org():
    with client() as c:
        r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
        assert r.status_code == 200
        assert r.json()["org"]["slug"] == "eaios"
