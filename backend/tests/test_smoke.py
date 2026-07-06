"""Smoke tests: auth flow, security primitives, RAG chunking, SQL guardrails, chat round-trip."""
from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def test_health():
    with client() as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_auth_and_chat_flow():
    with client() as c:
        # bootstrap admin exists
        r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
        assert r.status_code == 200
        token = r.json()["token"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = c.get("/api/auth/me", headers=headers)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

        # chat through orchestrator (mock LLM)
        r = c.post("/api/chat", json={"message": "How many users are in the database?"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["message"]["role"] == "assistant"
        assert "sql" in body["plan"]

        # wrong password rejected
        r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "wrong-password"})
        assert r.status_code == 401


def test_rbac_guard():
    with client() as c:
        r = c.post("/api/auth/register", json={"email": "emp@test.dev", "full_name": "Test Employee", "password": "password123"})
        assert r.status_code in (201, 409)
        r = c.post("/api/auth/login", json={"email": "emp@test.dev", "password": "password123"})
        token = r.json()["token"]["access_token"]
        r = c.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403  # employees cannot access admin


def test_jwt_roundtrip():
    from app.core.security import create_token, decode_token

    token = create_token("user-1", "admin")
    payload = decode_token(token)
    assert payload is not None and payload["sub"] == "user-1" and payload["role"] == "admin"
    assert decode_token(token + "tamper") is None


def test_chunking():
    from app.rag.chunking import chunk_blocks

    text = " ".join(f"Sentence number {i} about enterprise policy." for i in range(120))
    chunks = chunk_blocks([{"section": "Policy", "page": 1, "text": text}])
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 1200 for c in chunks)
    assert all(c["section"] == "Policy" for c in chunks)


def test_sql_guardrails():
    from app.agents.sql_agent import SQLAgent

    guard = SQLAgent.__new__(SQLAgent)  # no db needed for validation
    assert guard._validate("SELECT * FROM users") == ""
    assert guard._validate("DROP TABLE users") != ""
    assert guard._validate("SELECT 1; DELETE FROM users") != ""
    assert guard._validate("SELECT 1 -- comment") != ""
