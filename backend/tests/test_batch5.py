"""Batch-5 features: NL-to-BI dashboards, Agent Studio, Connectors."""
from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient, email="admin@eaios.dev", pw="admin12345") -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


# ── NL-to-BI dashboards ──────────────────────────────────────────────────
def test_chart_infer_types():
    from app.services.charts import infer_chart

    # categorical label + numeric value → bar
    spec = infer_chart("documents by type", ["doc_type", "total"],
                       [["pdf", 3], ["docx", 2], ["xlsx", 1]])
    assert spec["type"] == "bar" and spec["x"] == "doc_type" and spec["series"] == ["total"]
    assert spec["data"][0] == {"x": "pdf", "total": 3}

    # date-ish label → line
    spec = infer_chart("messages over time", ["day", "count"],
                       [["2026-07-01", 5], ["2026-07-02", 9], ["2026-07-03", 4]])
    assert spec["type"] == "line"

    # "share" keyword + few rows → pie
    spec = infer_chart("share of users by role", ["role", "n"], [["admin", 1], ["manager", 1], ["employee", 3]])
    assert spec["type"] == "pie"

    # single value → table
    spec = infer_chart("how many users", ["total"], [[7]])
    assert spec["type"] == "table"


def test_chart_endpoint_and_pin():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/dashboards/chart", headers=h, json={"question": "documents by type"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["type"] in ("bar", "line", "pie", "table")
        assert "SELECT" in body["sql"].upper()

        pin = c.post("/api/dashboards", headers=h, json={"question": body["question"], "sql": body["sql"], "spec": body})
        assert pin.status_code == 201
        cid = pin.json()["id"]

        lst = c.get("/api/dashboards", headers=h).json()
        assert any(x["id"] == cid for x in lst)

        assert c.delete(f"/api/dashboards/{cid}", headers=h).status_code == 204
        assert all(x["id"] != cid for x in c.get("/api/dashboards", headers=h).json())


# ── Agent Studio ─────────────────────────────────────────────────────────
def test_studio_crud_run_and_chat_route():
    with client() as c:
        h = _headers(c)
        # create
        r = c.post("/api/studio/agents", headers=h, json={
            "name": "HR Helper", "description": "Answers HR questions",
            "system_prompt": "You are a friendly HR assistant. Answer clearly and cite policy.",
            "tools": ["rag", "bogus"], "hue": 150,
        })
        assert r.status_code == 201, r.text
        agent = r.json()
        assert agent["slug"].startswith("studio_")
        assert agent["tools"] == ["rag"]  # invalid tool filtered out

        # appears in list
        assert any(a["id"] == agent["id"] for a in c.get("/api/studio/agents", headers=h).json())

        # test-run
        run = c.post(f"/api/studio/agents/{agent['id']}/run", headers=h, json={"input": "How many leave days do we get?"})
        assert run.status_code == 200
        assert run.json()["answer"]

        # invokable from chat via its slug (Route picker) — orchestrator resolves the custom agent
        chat = c.post("/api/chat", headers=h, json={"message": "What is the leave policy?", "agent": agent["slug"]})
        assert chat.status_code == 200
        assert chat.json()["message"]["agent"] == agent["slug"]

        # update
        up = c.put(f"/api/studio/agents/{agent['id']}", headers=h, json={
            "name": "HR Helper v2", "description": "", "system_prompt": "You are HR v2. Be concise.",
            "tools": [], "hue": 200, "enabled": True})
        assert up.status_code == 200 and up.json()["name"] == "HR Helper v2"

        # delete
        assert c.delete(f"/api/studio/agents/{agent['id']}", headers=h).status_code == 204


def test_studio_edit_rbac():
    with client() as c:
        admin = _headers(c)
        c.post("/api/auth/register", json={"email": "emp5@test.dev", "full_name": "Emp Five", "password": "password123"})
        emp = _headers(c, "emp5@test.dev", "password123")
        a = c.post("/api/studio/agents", headers=admin, json={
            "name": "Admin Bot", "system_prompt": "You are an admin-owned bot.", "tools": []}).json()
        # employee can't edit an agent they don't own
        r = c.put(f"/api/studio/agents/{a['id']}", headers=emp, json={
            "name": "hijack", "system_prompt": "changed by employee", "tools": []})
        assert r.status_code == 403


# ── Connectors ───────────────────────────────────────────────────────────
def test_connector_sample_sync_ingests_and_is_searchable():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/connectors/sync", headers=h, json={"provider": "sample"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["provider"] == "sample" and body["status"] == "connected"
        assert body["ingested"] >= 5

        # listed
        assert any(x["provider"] == "sample" for x in c.get("/api/connectors", headers=h).json())

        # the ingested docs are indexed and searchable via chat
        docs = c.get("/api/documents", headers=h).json()
        assert any("connector" in (d.get("tags") or "") for d in docs) or any(
            d["title"].startswith(("Gmail —", "Drive —")) for d in docs)

        # a structured table from the sample CSV should be queryable
        from app.core.database import SessionLocal
        from app.models import DataTable

        with SessionLocal() as db:
            assert db.query(DataTable).count() >= 1

        # cleanup: the shared test DB is session-scoped — remove the docs this
        # sync ingested so later suites (e.g. RAG-eval corpus checks) stay clean
        for d in c.get("/api/documents", headers=h).json():
            if "connector" in (d.get("tags") or ""):
                c.delete(f"/api/documents/{d['id']}", headers=h)


def test_connector_drive_requires_token():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/connectors/sync", headers=h, json={"provider": "google_drive"})
        assert r.status_code == 400
        assert "token" in r.json()["detail"].lower()
