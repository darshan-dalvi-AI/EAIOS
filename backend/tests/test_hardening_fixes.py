"""Regressions for the QA hardening pass — the behaviours that were wrong
before and must not drift back.

Each maps to a finding: analytics authorization (BUG-008), the task-list N+1
(BUG-018), unknown task status (BUG-014), token revocation on logout (BUG-015),
and pagination (BUG-019).
"""
import pytest
from sqlalchemy import event

from app.core.database import SessionLocal, engine
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
PW = "HardeningPass!2026"


def _workspace(slug: str) -> dict:
    r = client.post("/api/auth/signup", json={
        "company_name": f"{slug} Co", "full_name": f"{slug} Admin",
        "email": f"admin@{slug}hard.com", "password": PW})
    assert r.status_code in (200, 201), r.text
    admin = {"Authorization": "Bearer " + r.json()["token"]["access_token"]}
    client.post("/api/users", headers=admin, json={
        "email": f"emp@{slug}hard.com", "full_name": f"{slug} Emp",
        "password": PW, "role": "employee"})
    lr = client.post("/api/auth/login", json={"email": f"emp@{slug}hard.com", "password": PW})
    emp = {"Authorization": "Bearer " + lr.json()["token"]["access_token"]}
    return {"admin": admin, "emp": emp}


# ── BUG-008: analytics is a management view ─────────────────────────────────
def test_analytics_requires_admin_or_hr():
    w = _workspace("an")
    for ep in ("/api/analytics/usage", "/api/analytics/ai-usage", "/api/analytics/rag-eval"):
        assert client.get(ep, headers=w["admin"]).status_code == 200, ep
        assert client.get(ep, headers=w["emp"]).status_code == 403, ep


# ── BUG-014: an unknown task status is rejected, not silently coerced ───────
def test_unknown_task_status_is_rejected():
    w = _workspace("st")
    assert client.post("/api/tasks", headers=w["admin"],
                       json={"title": "valid", "status": "doing"}).status_code == 201
    r = client.post("/api/tasks", headers=w["admin"],
                    json={"title": "bad status", "status": "wat"})
    assert r.status_code == 422, r.text


# ── BUG-018: the task list is a constant number of queries, not one per row ─
def test_task_list_is_not_n_plus_one():
    w = _workspace("nn")
    for i in range(20):
        client.post("/api/tasks", headers=w["admin"], json={"title": f"Task {i}"})

    count = {"n": 0}
    listener = lambda *a, **k: count.__setitem__("n", count["n"] + 1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        r = client.get("/api/tasks", headers=w["admin"])
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert r.status_code == 200 and len(r.json()) >= 20
    # one for the tasks, one for the assignees — never one per task.
    assert count["n"] <= 4, f"{count['n']} queries for the task list — N+1 is back"


# ── BUG-019: list endpoints page ────────────────────────────────────────────
def test_task_list_paginates():
    w = _workspace("pg")
    for i in range(12):
        client.post("/api/tasks", headers=w["admin"], json={"title": f"Row {i}"})
    first = client.get("/api/tasks?limit=5", headers=w["admin"]).json()
    second = client.get("/api/tasks?limit=5&offset=5", headers=w["admin"]).json()
    assert len(first) == 5 and len(second) == 5
    assert {t["id"] for t in first}.isdisjoint({t["id"] for t in second})


# ── BUG-015: logout retires every token for the account ─────────────────────
def test_logout_invalidates_existing_tokens():
    w = _workspace("lo")
    assert client.get("/api/auth/me", headers=w["admin"]).status_code == 200
    assert client.post("/api/auth/logout", headers=w["admin"]).status_code == 200
    # the very same token must now be refused
    assert client.get("/api/auth/me", headers=w["admin"]).status_code == 401


def test_a_token_issued_after_logout_still_works():
    """Revocation is scoped to tokens issued *before* the logout, not the account."""
    w = _workspace("lo2")
    client.post("/api/auth/logout", headers=w["admin"])
    fresh = client.post("/api/auth/login", json={"email": "admin@lo2hard.com", "password": PW})
    assert fresh.status_code == 200
    tok = {"Authorization": "Bearer " + fresh.json()["token"]["access_token"]}
    assert client.get("/api/auth/me", headers=tok).status_code == 200
