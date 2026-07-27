"""The schema reporting on itself.

A column that stopped being globally unique in the models went on being
globally unique in the deployed database, and the only symptom was "a database
error occurred" on someone else's screen. Diagnosing it needed server logs.
These tests hold the endpoint that replaced that.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_a_healthy_schema_says_so():
    r = client.get("/api/health/schema")
    assert r.status_code == 200

    body = r.json()
    assert body["status"] == "ok", body
    assert body["stale_global_uniques"] == []
    assert body["version"]


def test_drift_is_reported_with_enough_detail_to_act_on(monkeypatch):
    from app.core import database as db_module

    monkeypatch.setattr(db_module, "stale_global_uniques", lambda: [
        {"table": "custom_agents", "column": "slug",
         "name": "ix_custom_agents_slug", "kind": "index"},
    ])

    body = client.get("/api/health/schema").json()

    assert body["status"] == "drifted"
    assert body["stale_global_uniques"][0]["table"] == "custom_agents"
    assert body["stale_global_uniques"][0]["column"] == "slug"
    assert "unique per workspace" in body["detail"]


def test_it_carries_no_data_and_no_configuration():
    """It answers without credentials, so it must not become a leak.

    Index names are structural. Rows, connection strings and settings are not,
    and none of them belong in a response anyone can read.
    """
    body = client.get("/api/health/schema").json()

    assert set(body) <= {"status", "version", "stale_global_uniques", "detail", "error"}
    flat = str(body).lower()
    for secret in ("password", "postgres://", "postgresql://", "@", "key=", "token"):
        assert secret not in flat, f"{secret!r} appeared in a public probe"


def test_a_broken_inspection_is_reported_rather_than_raised(monkeypatch):
    """A probe that 500s is worse than useless — it looks like the app is down."""
    from app.core import database as db_module

    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(db_module, "stale_global_uniques", boom)

    r = client.get("/api/health/schema")

    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
    assert "connection refused" in r.json()["error"]
