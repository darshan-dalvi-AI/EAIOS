"""Version control for code projects.

The properties worth defending: history is honest (a commit records what
actually changed), restoring is exact, storage does not grow with every commit
of an unchanged file, and one workspace's history is invisible to another.
"""
import secrets

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PW = "VcsTestPass!2026"


def _workspace(slug: str) -> dict:
    tag = secrets.token_hex(4)
    r = client.post("/api/auth/signup", json={
        "company_name": f"{slug}-{tag}", "full_name": f"{slug} Admin",
        "email": f"admin-{tag}@{slug}vcs.com", "password": PW})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


@pytest.fixture
def repo():
    """A project with two files, uncommitted."""
    h = _workspace("vcs")
    p = client.post("/api/projects", headers=h, json={"name": "Repo"}).json()
    f1 = client.post(f"/api/projects/{p['id']}/files", headers=h,
                     json={"path": "main.py", "content": "print(1)\n"}).json()
    client.post(f"/api/projects/{p['id']}/files", headers=h,
                json={"path": "util.py", "content": "X = 1\n"})
    return {"h": h, "pid": p["id"], "main": f1["id"]}


# ── committing ──────────────────────────────────────────────────────────────
def test_status_reports_uncommitted_files(repo):
    st = client.get(f"/api/projects/{repo['pid']}/status", headers=repo["h"]).json()
    assert st["clean"] is False
    assert set(st["added"]) == {"main.py", "util.py"}
    assert st["head"] is None


def test_commit_then_clean(repo):
    c = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                    json={"message": "initial"})
    assert c.status_code == 201, c.text
    assert c.json()["file_count"] == 2

    st = client.get(f"/api/projects/{repo['pid']}/status", headers=repo["h"]).json()
    assert st["clean"] is True, "the working tree should match the commit just made"


def test_an_empty_commit_is_refused(repo):
    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "one"})
    again = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                        json={"message": "nothing changed"})
    assert again.status_code == 409, "a commit recording no change is noise in the history"


def test_commits_form_a_parent_chain(repo):
    first = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                        json={"message": "first"}).json()
    client.put(f"/api/projects/files/{repo['main']}", headers=repo["h"],
               json={"content": "print(1)\nprint(2)\n"})
    second = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                         json={"message": "second"}).json()
    assert second["parent_id"] == first["id"]


# ── diffing ─────────────────────────────────────────────────────────────────
def test_diff_shows_only_what_changed(repo):
    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "base"})
    client.put(f"/api/projects/files/{repo['main']}", headers=repo["h"],
               json={"content": "print(1)\nprint(2)\n"})
    c2 = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                     json={"message": "add a line"}).json()

    detail = client.get(f"/api/projects/{repo['pid']}/commits/{c2['id']}",
                        headers=repo["h"]).json()
    changed = {f["path"]: f for f in detail["diff"]}
    assert set(changed) == {"main.py"}, "util.py did not change and must not appear"
    assert changed["main.py"]["change"] == "modified"
    assert changed["main.py"]["additions"] == 1
    assert "+print(2)" in changed["main.py"]["patch"]


def test_working_diff_before_committing(repo):
    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "base"})
    client.put(f"/api/projects/files/{repo['main']}", headers=repo["h"], json={"content": "changed\n"})

    d = client.get(f"/api/projects/{repo['pid']}/diff", headers=repo["h"]).json()
    assert d["kind"] == "working"
    assert [f["path"] for f in d["files"]] == ["main.py"]


# ── storage behaviour ───────────────────────────────────────────────────────
def test_unchanged_files_do_not_create_new_blobs(repo):
    """Content addressing: committing twice while editing one file of two must
    not store the untouched file again."""
    from app.core.database import SessionLocal
    from app.models import Blob

    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "one"})
    db = SessionLocal()
    try:
        after_first = db.query(Blob).count()
    finally:
        db.close()

    client.put(f"/api/projects/files/{repo['main']}", headers=repo["h"], json={"content": "v2\n"})
    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "two"})

    db = SessionLocal()
    try:
        after_second = db.query(Blob).count()
    finally:
        db.close()
    assert after_second == after_first + 1, "only the edited file should add a blob"


# ── restoring ───────────────────────────────────────────────────────────────
def test_checkout_restores_exact_content(repo):
    first = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                        json={"message": "v1"}).json()
    client.put(f"/api/projects/files/{repo['main']}", headers=repo["h"],
               json={"content": "totally different\n"})
    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "v2"})

    client.post(f"/api/projects/{repo['pid']}/checkout/{first['id']}", headers=repo["h"])

    back = client.get(f"/api/projects/files/{repo['main']}", headers=repo["h"]).json()
    assert back["content"] == "print(1)\n"


def test_checkout_rescues_uncommitted_work(repo):
    """Restoring must never silently throw away work someone forgot to commit."""
    first = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                        json={"message": "v1"}).json()
    client.put(f"/api/projects/files/{repo['main']}", headers=repo["h"],
               json={"content": "unsaved important work\n"})

    r = client.post(f"/api/projects/{repo['pid']}/checkout/{first['id']}",
                    headers=repo["h"]).json()
    assert r["rescued_to"], "uncommitted work was discarded instead of rescued"

    branches = {b["name"] for b in
                client.get(f"/api/projects/{repo['pid']}/branches", headers=repo["h"]).json()}
    assert r["rescued_to"] in branches


# ── branching ───────────────────────────────────────────────────────────────
def test_branch_starts_from_the_current_tip(repo):
    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "base"})
    made = client.post(f"/api/projects/{repo['pid']}/branches", headers=repo["h"],
                       json={"name": "feature-x", "from_branch": "main"})
    assert made.status_code == 201, made.text
    assert made.json()["branch"] == "feature-x"
    assert made.json()["file_count"] == 2


# ── isolation ───────────────────────────────────────────────────────────────
def test_one_workspace_cannot_read_anothers_history(repo):
    """Source history is as confidential as the source itself."""
    c1 = client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"],
                     json={"message": "secret architecture change"}).json()
    other = _workspace("intruder")

    pid = repo["pid"]
    assert client.get(f"/api/projects/{pid}/commits", headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/commits/{c1['id']}", headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/status", headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/branches", headers=other).status_code == 404
    assert client.get(f"/api/projects/{pid}/diff", headers=other).status_code == 404
    assert client.post(f"/api/projects/{pid}/checkout/{c1['id']}", headers=other).status_code == 404
    assert client.post(f"/api/projects/{pid}/commits", headers=other,
                       json={"message": "x"}).status_code == 404


def test_deleting_a_project_removes_its_history(repo):
    from app.core.database import SessionLocal
    from app.models import Commit, CommitFile

    client.post(f"/api/projects/{repo['pid']}/commits", headers=repo["h"], json={"message": "one"})
    assert client.delete(f"/api/projects/{repo['pid']}", headers=repo["h"]).status_code == 204

    db = SessionLocal()
    try:
        assert db.query(Commit).filter(Commit.project_id == repo["pid"]).count() == 0
        left = db.query(CommitFile).join(
            Commit, Commit.id == CommitFile.commit_id).filter(
            Commit.project_id == repo["pid"]).count()
        assert left == 0
    finally:
        db.close()
