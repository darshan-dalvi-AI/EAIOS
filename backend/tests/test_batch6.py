"""Batch-6: tasks/kanban, meeting→tasks, global search, compliance, metering, eval, website connector."""
from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient, email="admin@eaios.dev", pw="admin12345") -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


def test_tasks_crud_and_rbac():
    with client() as c:
        h = _headers(c)
        t = c.post("/api/tasks", headers=h, json={"title": "Prepare the demo environment"}).json()
        assert t["status"] == "todo" and t["source"] == "manual"
        moved = c.patch(f"/api/tasks/{t['id']}", headers=h, json={"status": "doing"}).json()
        assert moved["status"] == "doing"
        assert c.patch(f"/api/tasks/{t['id']}", headers=h, json={"status": "flying"}).status_code == 400
        assert any(x["id"] == t["id"] for x in c.get("/api/tasks", headers=h).json())
        # non-owner employee cannot delete
        c.post("/api/auth/register", json={"email": "emp6@test.dev", "password": "demo12345", "full_name": "Emp Six"})
        he = _headers(c, "emp6@test.dev", "demo12345")
        assert c.delete(f"/api/tasks/{t['id']}", headers=he).status_code == 403
        assert c.delete(f"/api/tasks/{t['id']}", headers=h).status_code == 204


def test_meeting_minutes_create_tasks():
    with client() as c:
        h = _headers(c)
        transcript = ("Maya said we must update the security policy by Friday. "
                      "Dev will prepare the demo environment. We decided to ship on Monday.")
        r = c.post("/api/agents/meeting", headers=h,
                   json={"transcript": transcript, "title": "Batch6 Sync", "save_to_knowledge": False})
        assert r.status_code == 200
        body = r.json()
        assert "minutes" in body and body["tasks_created"] >= 1
        titles = [t["title"].lower() for t in c.get("/api/tasks", headers=h).json()]
        assert any(t["source"] == "meeting" for t in c.get("/api/tasks", headers=h).json())
        assert any("policy" in x or "demo" in x for x in titles)


def test_global_search_groups():
    with client() as c:
        h = _headers(c)
        r = c.get("/api/search", headers=h, params={"q": "policy"})
        assert r.status_code == 200
        body = r.json()
        for key in ("documents", "passages", "entities", "tables", "messages"):
            assert key in body


def test_compliance_export_and_erase():
    with client() as c:
        h = _headers(c)
        c.post("/api/chat", headers=h, json={"message": "What is the leave policy?"})
        exp = c.get("/api/me/export", headers=h)
        assert exp.status_code == 200
        data = exp.json()
        assert data["user"]["email"] == "admin@eaios.dev"
        assert len(data["conversations"]) >= 1
        erase = c.delete("/api/me/data", headers=h)
        assert erase.status_code == 200
        assert erase.json()["removed"]["conversations"] >= 1
        assert c.get("/api/me/export", headers=h).json()["conversations"] == []


def test_usage_metering_and_rag_eval():
    with client() as c:
        h = _headers(c)
        c.post("/api/chat", headers=h, json={"message": "How many vacation days do we get?"})
        usage = c.get("/api/analytics/ai-usage", headers=h)
        assert usage.status_code == 200
        assert any(row["requests"] >= 1 for row in usage.json()["by_user"])
        ev = c.get("/api/analytics/rag-eval", headers=h)
        assert ev.status_code == 200
        assert "hit_rate" in ev.json()


def test_website_connector_blocks_private_hosts():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/connectors/sync", headers=h,
                   json={"provider": "website", "token": "http://localhost:8000/admin"})
        assert r.status_code == 400
        r2 = c.post("/api/connectors/sync", headers=h, json={"provider": "website", "token": ""})
        assert r2.status_code == 400
