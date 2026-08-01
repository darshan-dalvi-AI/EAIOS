"""Collaborative code projects.

Source code is the most sensitive thing a workspace can hold, so these tests
care about two properties above all: one workspace can never reach another's
project, and deleting something takes its children with it rather than leaving
orphans behind.
"""
import secrets

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PW = "CodeProjectPass!2026"


def _workspace(slug: str) -> dict:
    """A fresh workspace per test — the suite shares one database, so a fixed
    address would collide with the previous test's signup."""
    tag = secrets.token_hex(4)
    r = client.post("/api/auth/signup", json={
        "company_name": f"{slug}-{tag} Co", "full_name": f"{slug} Admin",
        "email": f"admin-{tag}@{slug}code.com", "password": PW})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


@pytest.fixture
def alpha():
    return _workspace("alpha")


@pytest.fixture
def beta():
    return _workspace("beta")


def _project_with_file(h, name="Svc", path="src/main.py", content="print('hi')\n"):
    p = client.post("/api/projects", headers=h, json={"name": name}).json()
    f = client.post(f"/api/projects/{p['id']}/files", headers=h,
                    json={"path": path, "content": content}).json()
    return p, f


# ── the basics ──────────────────────────────────────────────────────────────
def test_create_project_and_file(alpha):
    p, f = _project_with_file(alpha)
    assert p["id"] and f["path"] == "src/main.py"
    assert f["language"] == "python", "language should be inferred from the extension"
    assert f["content"] == "print('hi')\n"


def test_saving_keeps_a_version_history(alpha):
    _, f = _project_with_file(alpha)
    client.put(f"/api/projects/files/{f['id']}", headers=alpha,
               json={"content": "print('v2')\n", "note": "second"})
    body = client.get(f"/api/projects/files/{f['id']}", headers=alpha).json()
    assert body["content"] == "print('v2')\n"

    versions = client.get(f"/api/projects/files/{f['id']}/versions", headers=alpha).json()
    assert len(versions) == 1, "the previous text should have been snapshotted"


def test_a_version_can_be_restored(alpha):
    _, f = _project_with_file(alpha, content="original\n")
    client.put(f"/api/projects/files/{f['id']}", headers=alpha, json={"content": "changed\n"})
    v = client.get(f"/api/projects/files/{f['id']}/versions", headers=alpha).json()[0]

    restored = client.post(f"/api/projects/files/{f['id']}/restore/{v['id']}",
                           headers=alpha).json()
    assert restored["content"] == "original\n"


@pytest.mark.parametrize("path", ["../../etc/passwd", "/../secrets", "a/../../b"])
def test_path_traversal_is_refused(alpha, path):
    p = client.post("/api/projects", headers=alpha, json={"name": "T"}).json()
    r = client.post(f"/api/projects/{p['id']}/files", headers=alpha, json={"path": path})
    assert r.status_code == 422, f"{path!r} was accepted"


def test_duplicate_path_in_one_project_is_refused(alpha):
    p, _ = _project_with_file(alpha)
    r = client.post(f"/api/projects/{p['id']}/files", headers=alpha,
                    json={"path": "src/main.py"})
    assert r.status_code == 409


# ── isolation: the property that matters most ───────────────────────────────
def test_one_workspace_cannot_reach_anothers_code(alpha, beta):
    p, f = _project_with_file(alpha, name="Alpha Secret Service",
                              content="ALPHA_API_KEY = 'confidential'\n")

    # Every route, with a valid beta token and a correct alpha id.
    assert client.get(f"/api/projects/{p['id']}/files", headers=beta).status_code == 404
    assert client.get(f"/api/projects/files/{f['id']}", headers=beta).status_code == 404
    assert client.put(f"/api/projects/files/{f['id']}", headers=beta,
                      json={"content": "PWNED"}).status_code == 404
    assert client.delete(f"/api/projects/files/{f['id']}", headers=beta).status_code == 404
    assert client.delete(f"/api/projects/{p['id']}", headers=beta).status_code == 404
    assert client.get(f"/api/projects/files/{f['id']}/versions",
                      headers=beta).status_code == 404

    # Beta's listing must not mention alpha's project at all.
    listed = client.get("/api/projects", headers=beta).json()
    assert all(x["name"] != "Alpha Secret Service" for x in listed)

    # And alpha's file is untouched by any of it.
    still = client.get(f"/api/projects/files/{f['id']}", headers=alpha).json()
    assert still["content"] == "ALPHA_API_KEY = 'confidential'\n"


def test_deleting_a_project_removes_its_files_and_versions(alpha):
    from app.core.database import SessionLocal
    from app.models import FileVersion, ProjectFile

    p, f = _project_with_file(alpha)
    client.put(f"/api/projects/files/{f['id']}", headers=alpha, json={"content": "v2"})

    assert client.delete(f"/api/projects/{p['id']}", headers=alpha).status_code == 204

    db = SessionLocal()
    try:
        assert db.query(ProjectFile).filter(ProjectFile.project_id == p["id"]).count() == 0
        assert db.query(FileVersion).filter(FileVersion.file_id == f["id"]).count() == 0
    finally:
        db.close()


def test_the_sql_guard_knows_about_the_new_tables(alpha):
    """A tenant table the guard does not know is a table it will not scope."""
    from app.agents.sql_agent import tenant_tables

    known = tenant_tables()
    for t in ("projects", "project_files", "file_versions"):
        assert t in known, f"{t} is not covered by the SQL tenant guard"
