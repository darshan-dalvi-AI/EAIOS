"""Granular PII audit flagging — agents touching sensitive Knowledge-Graph
entities (people, emails, phones) leave a ``pii.access`` trail + live event."""
import json

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient) -> dict:
    r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


DIRECTORY = (
    "Contact directory. Dr. Maya Iyer leads the Finance Committee and reviews budgets. "
    "Dr. Maya Iyer works closely with Mr. Rohan Mehta on quarterly planning. "
    "Mr. Rohan Mehta manages the Sales Group. "
    "Reach the desk at +91 (22) 4890-1234 or maya.iyer@eaios.dev for escalations."
)


def test_sensitive_classification():
    from app.services.kgraph import SENSITIVE_TYPES, _classify, sensitive_names

    assert _classify("maya.iyer@eaios.dev", "") == "email"
    assert _classify("+91 (22) 4890-1234", "") == "phone"
    assert _classify("Finance Committee", "") == "org"
    assert {"person", "email", "phone"} == SENSITIVE_TYPES

    rel = {
        "a": {"id": "1", "name": "Maya Iyer", "type": "person"},
        "b": {"id": "2", "name": "Sales Group", "type": "org"},
        "path": [{"id": "3", "name": "maya.iyer@eaios.dev", "type": "email"}],
    }
    assert sensitive_names(rel) == ["Maya Iyer", "maya.iyer@eaios.dev"]
    assert sensitive_names(None) == []


def _upload_directory(c: TestClient, h: dict) -> None:
    r = c.post("/api/documents/upload", headers=h,
               files={"file": ("contact_directory.txt", DIRECTORY.encode(), "text/plain")})
    assert r.status_code == 201


def _pii_rows(source: str) -> list:
    from app.core.database import SessionLocal
    from app.models import AuditLog

    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(AuditLog.action == "pii.access").all()
        return [json.loads(r.detail) for r in rows if json.loads(r.detail)["source"] == source]


def test_graph_relate_flags_pii_access():
    with client() as c:
        h = _headers(c)
        _upload_directory(c, h)
        r = c.get("/api/graph/relate", params={"a": "Maya Iyer", "b": "Rohan Mehta"}, headers=h)
        assert r.status_code == 200
        assert r.json()["a"]["type"] == "person"

        flagged = _pii_rows("graph.relate")
        assert flagged, "expected a pii.access audit entry for graph.relate"
        assert any("Maya Iyer" in f["entities"] for f in flagged)

        # security event surfaced on the realtime feed (REST replay)
        events = c.get("/api/events/recent").json()
        assert any(e["type"] == "security.pii" and e["source"] == "graph.relate" for e in events)


def test_document_agent_relational_query_flags_pii():
    with client() as c:
        h = _headers(c)
        _upload_directory(c, h)
        r = c.post("/api/chat", json={"message": "How are Maya Iyer and Rohan Mehta related?"}, headers=h)
        assert r.status_code == 200

        flagged = _pii_rows("document_agent.graph")
        assert flagged, "expected a pii.access audit entry from the Document Agent"
        names = {n for f in flagged for n in f["entities"]}
        assert {"Maya Iyer", "Rohan Mehta"} <= names
