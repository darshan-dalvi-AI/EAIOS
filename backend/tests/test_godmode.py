"""God-Mode batch: OpenRouter provider naming + temperature, runtime model
switch, self-correcting SQL, and Human-in-the-Loop workflow approvals."""
import json

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient, email="admin@eaios.dev", pw="admin12345") -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


# ── OpenRouter provider detection ────────────────────────────────────────
def test_openrouter_provider_naming(monkeypatch):
    from app.core.config import settings
    from app.llm.provider import OpenAILLM

    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "google/gemini-2.0-flash-001")
    llm = OpenAILLM()
    assert llm.name == "openrouter"
    assert llm.model == "google/gemini-2.0-flash-001"

    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    assert OpenAILLM().name == "groq"


# ── runtime model switching ──────────────────────────────────────────────
def test_admin_model_switch_and_reset():
    with client() as c:
        headers = _headers(c)
        r = c.post("/api/admin/model",
                   json={"provider": "openai", "base_url": "https://openrouter.ai/api/v1",
                         "model": "deepseek/deepseek-chat", "temperature": 0.7},
                   headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["active_provider"] == "openrouter"
        assert body["active_model"] == "deepseek/deepseek-chat"
        assert body["temperature"] == 0.7

        cfg = c.get("/api/admin/config", headers=headers).json()
        assert cfg["active_provider"] == "openrouter"
        assert cfg["temperature"] == 0.7

        # restore mock so later tests stay deterministic
        c.post("/api/admin/model", json={"provider": "mock"}, headers=headers)


def test_model_switch_requires_admin():
    with client() as c:
        c.post("/api/auth/register",
               json={"email": "emp2@test.dev", "full_name": "Emp Two", "password": "password123"})
        emp = _headers(c, "emp2@test.dev", "password123")
        r = c.post("/api/admin/model", json={"provider": "mock"}, headers=emp)
        assert r.status_code == 403


def test_model_switch_validation():
    with client() as c:
        headers = _headers(c)
        assert c.post("/api/admin/model", json={"provider": "banana"}, headers=headers).status_code == 422
        assert c.post("/api/admin/model", json={"base_url": "http://insecure"}, headers=headers).status_code == 422
        assert c.post("/api/admin/model", json={"temperature": 3.0}, headers=headers).status_code == 422


# ── self-correcting SQL ──────────────────────────────────────────────────
def test_sql_reflection_recovers_from_error(monkeypatch):
    """First generated query errors; the reflection loop rewrites it to a
    valid one and the agent still returns rows."""
    from app.agents import sql_agent as mod
    from app.core.database import SessionLocal
    from app.models import User

    calls = {"n": 0}
    monkeypatch.setattr(mod.SQLAgent, "_generate",
                        lambda self, q: "SELECT COUNT(*) AS total FROM nonexistent_table")

    def fake_reflect(self, question, failed_sql, error):
        calls["n"] += 1
        return "SELECT COUNT(*) AS total FROM users"
    monkeypatch.setattr(mod.SQLAgent, "_reflect", fake_reflect)

    with client() as c:  # ensures bootstrap admin exists
        c.get("/api/health")
    with SessionLocal() as db:
        user = db.query(User).first()
        out = mod.SQLAgent(db, user).answer("how many users are there")
        assert calls["n"] == 1, "reflection loop did not fire"
        assert not out.warning
        assert "Self-corrected" in out.explanation
        assert out.rows and out.rows[0][0] >= 1


# ── Human-in-the-Loop approvals ──────────────────────────────────────────
def _hitl_workflow_body():
    return {
        "name": "Sensitive email (HITL)",
        "trigger": "manual",
        "nodes": [
            {"id": "t", "type": "trigger", "x": 0, "y": 0, "data": {"label": "Manual"}},
            {"id": "a", "type": "agent", "x": 0, "y": 0,
             "data": {"agent": "document", "prompt": "Summarize: {{input}}"}},
            {"id": "ap", "type": "approve", "x": 0, "y": 0,
             "data": {"label": "Manager sign-off", "message": "Approve before emailing HR"}},
            {"id": "n", "type": "notify", "x": 0, "y": 0, "data": {"message": "Email sent for {{workflow}}"}},
        ],
        "edges": [{"from": "t", "to": "a"}, {"from": "a", "to": "ap"}, {"from": "ap", "to": "n"}],
        "enabled": True,
    }


def test_workflow_pauses_at_approve_then_resumes():
    with client() as c:
        headers = _headers(c)
        wf_id = c.post("/api/workflows", json=_hitl_workflow_body(), headers=headers).json()["id"]

        # run → should pause at the approve node
        run = c.post(f"/api/workflows/{wf_id}/run", json={"input": "annual leave policy"}, headers=headers).json()
        assert run["status"] == "awaiting_approval"
        log = json.loads(run["log"])
        assert any(e["type"] == "approve" and e["status"] == "awaiting" for e in log)
        assert not any(e["type"] == "notify" for e in log)  # notify hasn't fired yet
        run_id = run["id"]

        # approve → resumes and completes, notify fires
        resumed = c.post(f"/api/workflows/runs/{run_id}/approve", json={"approved": True}, headers=headers).json()
        assert resumed["status"] == "ok"
        log2 = json.loads(resumed["log"])
        assert any(e["type"] == "approve" and e["label"] == "approved" for e in log2)
        assert any(e["type"] == "notify" for e in log2)


def test_workflow_reject_halts_run():
    with client() as c:
        headers = _headers(c)
        wf_id = c.post("/api/workflows", json=_hitl_workflow_body(), headers=headers).json()["id"]
        run = c.post(f"/api/workflows/{wf_id}/run", json={"input": "x"}, headers=headers).json()
        assert run["status"] == "awaiting_approval"
        rejected = c.post(f"/api/workflows/runs/{run['id']}/approve",
                          json={"approved": False}, headers=headers).json()
        assert rejected["status"] == "error"
        assert not any(e["type"] == "notify" for e in json.loads(rejected["log"]))


def test_approve_requires_privilege():
    with client() as c:
        admin = _headers(c)
        wf_id = c.post("/api/workflows", json=_hitl_workflow_body(), headers=admin).json()["id"]
        run = c.post(f"/api/workflows/{wf_id}/run", json={"input": "x"}, headers=admin).json()

        c.post("/api/auth/register",
               json={"email": "emp3@test.dev", "full_name": "Emp Three", "password": "password123"})
        emp = _headers(c, "emp3@test.dev", "password123")
        r = c.post(f"/api/workflows/runs/{run['id']}/approve", json={"approved": True}, headers=emp)
        assert r.status_code == 403
