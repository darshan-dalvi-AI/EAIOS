"""Importing a file or a folder into the Code app.

The filtering is the whole feature. "Open this folder" on a real repository
hands the browser tens of thousands of files, almost all of them dependencies
and build output, so an import that faithfully uploads what it was given is
useless. These tests pin what gets dropped and — just as importantly — that the
person is told about it.
"""
import pytest
from fastapi.testclient import TestClient

from app.api.routes.projects import (
    MAX_FILES_PER_PROJECT, MAX_IMPORT_FILES, import_skip_reason,
)
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _auth(c: TestClient, company: str, email: str) -> dict:
    r = c.post("/api/auth/signup", json={"company_name": company, "full_name": "Dev One",
                                         "email": email, "password": "welcome123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


def _imp(c, h, files, **kw):
    return c.post("/api/projects/import", headers=h, json={"files": files, **kw})


# ── the filter, in isolation ──────────────────────────────────────────────

@pytest.mark.parametrize("path, reason_contains", [
    ("node_modules/react/index.js", "node_modules"),
    ("app/node_modules/x/y.js", "node_modules"),
    (".git/config", ".git"),
    ("__pycache__/mod.cpython-312.pyc", "__pycache__"),
    ("frontend/dist/bundle.js", "dist"),
    (".venv/lib/site.py", ".venv"),
    ("logo.png", "not a text file"),
    ("report.pdf", "not a text file"),
    ("package-lock.json", "generated file"),
    ("yarn.lock", "generated file"),
])
def test_junk_is_skipped(path, reason_contains):
    reason = import_skip_reason(path, 10, "x")
    assert reason and reason_contains in reason


@pytest.mark.parametrize("path", [
    "src/main.py", "README.md", "app/components/Button.tsx",
    "Makefile", "deploy/k8s.yaml", "query.sql", ".env.example",
])
def test_real_source_files_are_kept(path):
    assert import_skip_reason(path, 100, "print('hi')") is None


def test_a_binary_file_with_an_innocent_name_is_caught():
    """Extension checks alone miss a compiled artefact named .dat or with no
    extension at all. A NUL byte is the reliable tell — text encodings do not
    produce one."""
    assert import_skip_reason("data/model.dat", 50, "GIF89a\x00\x01") == "looks binary"
    assert import_skip_reason("bundle", 50, "\x00\x00") == "looks binary"


def test_an_oversized_file_is_skipped_not_truncated():
    reason = import_skip_reason("big.csv", 999_999, "a")
    assert reason and "larger than" in reason


# ── the endpoint ──────────────────────────────────────────────────────────

def test_import_creates_a_project_named_after_the_folder(client):
    h = _auth(client, "Imp One", "imp1@example.com")
    r = _imp(client, h, [
        {"path": "src/main.py", "content": "print(1)"},
        {"path": "src/util.py", "content": "x = 2"},
        {"path": "README.md", "content": "# hi"},
    ], name="my-app")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project"]["name"] == "my-app"
    assert body["imported"] == 3
    # Most files are Python, so that is what the project is labelled.
    assert body["project"]["language"] == "python"


def test_folder_structure_survives_the_import(client):
    h = _auth(client, "Imp Two", "imp2@example.com")
    r = _imp(client, h, [{"path": "a/b/c/deep.py", "content": "pass"}], name="nested")
    pid = r.json()["project"]["id"]
    files = client.get(f"/api/projects/{pid}/files", headers=h).json()
    assert [f["path"] for f in files] == ["a/b/c/deep.py"]


def test_the_skip_report_names_files_and_reasons(client):
    """Skipping silently is how somebody spends ten minutes hunting for a file
    that was never uploaded."""
    h = _auth(client, "Imp Three", "imp3@example.com")
    r = _imp(client, h, [
        {"path": "src/app.py", "content": "ok"},
        {"path": "node_modules/left-pad/index.js", "content": "junk"},
        {"path": "icon.png", "content": "\x89PNG"},
        {"path": "package-lock.json", "content": "{}"},
    ], name="mixed")
    body = r.json()
    assert body["imported"] == 1
    assert body["skipped_total"] == 3
    reported = {s["path"]: s["reason"] for s in body["skipped"]}
    assert "node_modules" in reported["node_modules/left-pad/index.js"]
    assert reported["icon.png"] == "not a text file"
    assert reported["package-lock.json"] == "generated file"


def test_importing_into_an_existing_project_keeps_what_is_there(client):
    h = _auth(client, "Imp Four", "imp4@example.com")
    pid = client.post("/api/projects", headers=h,
                      json={"name": "existing"}).json()["id"]
    client.post(f"/api/projects/{pid}/files", headers=h,
                json={"path": "old.py", "content": "old"})

    r = _imp(client, h, [{"path": "new.py", "content": "new"}], project_id=pid)
    assert r.status_code == 201
    paths = {f["path"] for f in client.get(f"/api/projects/{pid}/files", headers=h).json()}
    assert paths == {"old.py", "new.py"}


def test_an_existing_file_is_never_overwritten(client):
    """Someone may have that file open. Report it, do not replace it."""
    h = _auth(client, "Imp Five", "imp5@example.com")
    pid = client.post("/api/projects", headers=h, json={"name": "p"}).json()["id"]
    client.post(f"/api/projects/{pid}/files", headers=h,
                json={"path": "keep.py", "content": "ORIGINAL"})

    r = _imp(client, h, [
        {"path": "keep.py", "content": "REPLACED"},
        {"path": "other.py", "content": "fresh"},
    ], project_id=pid)
    assert r.json()["imported"] == 1
    assert any("already" in s["reason"] for s in r.json()["skipped"])

    files = client.get(f"/api/projects/{pid}/files", headers=h).json()
    fid = next(f["id"] for f in files if f["path"] == "keep.py")
    assert client.get(f"/api/projects/files/{fid}", headers=h).json()["content"] == "ORIGINAL"


def test_an_all_junk_folder_leaves_no_empty_project_behind(client):
    """Filtering happens before the project is created, so a folder that is
    entirely dependencies does not litter the sidebar with an empty shell."""
    h = _auth(client, "Imp Six", "imp6@example.com")
    before = len(client.get("/api/projects", headers=h).json())
    r = _imp(client, h, [
        {"path": "node_modules/a/index.js", "content": "x"},
        {"path": ".git/HEAD", "content": "ref"},
    ], name="junk")
    assert r.status_code == 422
    assert len(client.get("/api/projects", headers=h).json()) == before


def test_traversal_paths_are_skipped_not_stored(client):
    h = _auth(client, "Imp Seven", "imp7@example.com")
    r = _imp(client, h, [
        {"path": "../../etc/passwd", "content": "root:x"},
        {"path": "ok.py", "content": "fine"},
    ], name="trav")
    assert r.json()["imported"] == 1
    pid = r.json()["project"]["id"]
    paths = [f["path"] for f in client.get(f"/api/projects/{pid}/files", headers=h).json()]
    assert paths == ["ok.py"]


def test_too_many_files_is_refused_with_a_useful_message(client):
    h = _auth(client, "Imp Eight", "imp8@example.com")
    files = [{"path": f"f{i}.py", "content": "x"} for i in range(MAX_IMPORT_FILES + 1)]
    r = _imp(client, h, files, name="huge")
    assert r.status_code == 413
    assert "subfolder" in r.json()["detail"]


def test_the_per_project_file_cap_still_holds(client):
    h = _auth(client, "Imp Nine", "imp9@example.com")
    files = [{"path": f"src/f{i}.py", "content": "x"} for i in range(MAX_FILES_PER_PROJECT + 20)]
    r = _imp(client, h, files, name="capped")
    body = r.json()
    assert body["imported"] == MAX_FILES_PER_PROJECT
    assert any("limit" in s["reason"] for s in body["skipped"])


def test_import_needs_a_session(client):
    r = client.post("/api/projects/import", json={"files": [{"path": "a.py", "content": "x"}]})
    assert r.status_code == 401


def test_one_workspace_cannot_import_into_another(client):
    """The project id is attacker-controlled, so it has to be resolved through
    the tenant-scoped lookup rather than trusted."""
    a = _auth(client, "Alpha Co", "alpha@example.com")
    b = _auth(client, "Beta Co", "beta@example.com")
    pid = client.post("/api/projects", headers=a, json={"name": "alpha-only"}).json()["id"]

    r = _imp(client, b, [{"path": "sneak.py", "content": "x"}], project_id=pid)
    assert r.status_code == 404
    assert client.get(f"/api/projects/{pid}/files", headers=a).json() == []
