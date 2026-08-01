"""Code projects — the collaborative editing workspace.

A project holds files; files hold text plus a CRDT document so several people
can edit the same file at once (see core/collab.py). Everything here is an
ordinary tenant object: the session-level filter scopes every query to the
caller's workspace, and because these tables carry ``org_id`` they are also
covered by the database Row-Level Security policy without further work.
"""
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Commit, FileVersion, Project, ProjectFile, User
from app.services import audit, vcs

router = APIRouter(prefix="/projects", tags=["projects"])

MAX_FILE_BYTES = 512_000        # a source file, not an asset store
MAX_FILES_PER_PROJECT = 200
MAX_VERSIONS_KEPT = 50

# ── folder import ────────────────────────────────────────────────────────
# The browser hands over whatever the person picked, so "open this folder" on a
# real repository arrives as tens of thousands of files, nearly all of them
# dependencies and build output. The editor filters before uploading, but that
# is a convenience, not a control: anything a client decides can be skipped by
# a client. These limits are the ones that actually hold.
MAX_IMPORT_FILES = 400          # examined per request, before filtering
MAX_IMPORT_TOTAL_BYTES = 8_000_000

# Directory names that are never worth importing into an editor: package
# installs, VCS metadata, build output, caches, virtualenvs.
SKIP_DIRS = frozenset({
    "node_modules", ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "venv", ".venv", "env",
    "dist", "build", "out", "target", "coverage", ".next", ".nuxt", ".cache",
    "vendor", "Pods", ".terraform", "bin", "obj", ".gradle", ".tox", "site-packages",
})

# Extensions that cannot be edited as text. Kept as a denylist rather than an
# allowlist so an unusual source extension still imports.
SKIP_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svgz", ".tiff",
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".jar", ".war", ".bz2", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".pyc", ".pyo", ".o", ".a",
    ".mp3", ".mp4", ".mov", ".avi", ".wav", ".flac", ".webm", ".mkv", ".ogg",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3", ".pkl", ".npy", ".parquet", ".wasm",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
})

# Generated files that are text but never worth reading or editing.
SKIP_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "composer.lock", "Gemfile.lock", ".DS_Store", "Thumbs.db",
})


def import_skip_reason(path: str, size: int, content: str) -> str | None:
    """Why this file should not be imported, or None to keep it.

    Returns a human-readable reason because the person is told what was left
    out — a silent skip is how somebody spends ten minutes looking for a file
    that was never uploaded.
    """
    parts = path.split("/")
    for seg in parts[:-1]:
        if seg in SKIP_DIRS:
            return f"inside {seg}/"
    name = parts[-1]
    if name in SKIP_NAMES:
        return "generated file"
    if os.path.splitext(name)[1].lower() in SKIP_SUFFIXES:
        return "not a text file"
    if size > MAX_FILE_BYTES:
        return f"larger than {MAX_FILE_BYTES // 1000} KB"
    # A NUL byte is the oldest and most reliable binary test there is: text
    # encodings do not produce one, and an extension check alone misses a
    # compiled artefact that happens to be named .dat or has no extension.
    if "\x00" in content:
        return "looks binary"
    return None

# path suffix → Monaco language id
_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".java": "java", ".c": "c", ".h": "c", ".cpp": "cpp",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".sql": "sql", ".html": "html", ".css": "css", ".scss": "scss",
    ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".md": "markdown",
    ".sh": "shell", ".xml": "xml", ".txt": "plaintext",
}


def language_for(path: str) -> str:
    return _LANG.get(os.path.splitext(path)[1].lower(), "plaintext")


def safe_path(raw: str) -> str:
    """Normalise a project-relative path and refuse anything that escapes it.

    Paths are stored, not written to disk, but they are displayed and used as
    identifiers — so traversal segments are rejected rather than sanitised, to
    keep what the user typed and what is stored identical."""
    p = (raw or "").strip().replace("\\", "/").lstrip("/")
    if not p or len(p) > 300:
        raise HTTPException(422, "A file path is required (max 300 characters).")
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise HTTPException(422, "File paths cannot contain '..'.")
    return "/".join(parts)


# ── schemas ──────────────────────────────────────────────────────────────
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=400)
    language: str = Field(default="python", max_length=30)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    language: str | None = Field(default=None, max_length=30)


class FileIn(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(default="")


class FileSave(BaseModel):
    content: str
    note: str = Field(default="", max_length=200)


class ImportFile(BaseModel):
    # Deliberately not `FileIn`: an import carries paths the browser produced
    # rather than paths a person typed, so over-length and traversal segments
    # are reported as skipped files instead of failing the whole upload.
    path: str = Field(max_length=1000)
    content: str = Field(default="")


class ImportIn(BaseModel):
    files: list[ImportFile]
    project_id: str | None = None     # omit to create a new project
    name: str = Field(default="", max_length=120)


def _project_out(p: Project, file_count: int = 0) -> dict:
    return {"id": p.id, "name": p.name, "description": p.description,
            "language": p.language, "owner_id": p.owner_id, "files": file_count,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat()}


def _file_out(f: ProjectFile, with_content: bool = False) -> dict:
    out = {"id": f.id, "project_id": f.project_id, "path": f.path,
           "language": f.language, "size_bytes": f.size_bytes,
           "updated_by": f.updated_by, "updated_at": f.updated_at.isoformat()}
    if with_content:
        out["content"] = f.content
    return out


def _get_project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


def _get_file(db: Session, file_id: str) -> ProjectFile:
    f = db.get(ProjectFile, file_id)
    if f is None:
        raise HTTPException(404, "File not found")
    return f


# ── projects ─────────────────────────────────────────────────────────────
@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                  limit: int = Query(100, ge=1, le=300), offset: int = Query(0, ge=0)):
    rows = list(db.scalars(select(Project).order_by(Project.updated_at.desc())
                           .limit(limit).offset(offset)))
    if not rows:
        return []
    counts = dict(db.execute(
        select(ProjectFile.project_id, func.count(ProjectFile.id))
        .where(ProjectFile.project_id.in_([p.id for p in rows]))
        .group_by(ProjectFile.project_id)).all())
    return [_project_out(p, counts.get(p.id, 0)) for p in rows]


@router.post("", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    p = Project(name=body.name.strip(), description=body.description.strip(),
                language=body.language.strip() or "python", owner_id=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    audit.log(db, "project.create", user.id, p.name)
    return _project_out(p, 0)


@router.patch("/{project_id}")
def update_project(project_id: str, body: ProjectPatch, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    p = _get_project(db, project_id)
    if body.name is not None:
        p.name = body.name.strip()
    if body.description is not None:
        p.description = body.description.strip()
    if body.language is not None:
        p.language = body.language.strip()
    db.commit()
    return _project_out(p)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    p = _get_project(db, project_id)
    # Only the creator or an admin may delete a whole project — it takes every
    # file and every version with it.
    if p.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the project creator or an admin can delete it")
    name = p.name
    db.delete(p)          # files cascade; versions cascade from files
    db.commit()
    audit.log(db, "project.delete", user.id, name)


# ── files ────────────────────────────────────────────────────────────────
@router.get("/{project_id}/files")
def list_files(project_id: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    _get_project(db, project_id)
    rows = db.scalars(select(ProjectFile)
                      .where(ProjectFile.project_id == project_id)
                      .order_by(ProjectFile.path))
    return [_file_out(f) for f in rows]


@router.post("/{project_id}/files", status_code=201)
def create_file(project_id: str, body: FileIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _get_project(db, project_id)
    path = safe_path(body.path)
    content = body.content or ""
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise HTTPException(413, f"A file is limited to {MAX_FILE_BYTES // 1000} KB.")

    existing = db.scalar(select(ProjectFile).where(
        ProjectFile.project_id == project_id, ProjectFile.path == path))
    if existing is not None:
        raise HTTPException(409, f"'{path}' already exists in this project")

    count = db.scalar(select(func.count(ProjectFile.id))
                      .where(ProjectFile.project_id == project_id)) or 0
    if count >= MAX_FILES_PER_PROJECT:
        raise HTTPException(409, f"A project is limited to {MAX_FILES_PER_PROJECT} files.")

    f = ProjectFile(project_id=project_id, path=path, language=language_for(path),
                    content=content, size_bytes=len(content.encode("utf-8")),
                    updated_by=user.id)
    db.add(f)
    db.commit()
    db.refresh(f)
    return _file_out(f, with_content=True)


@router.post("/import", status_code=201)
def import_files(body: ImportIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Import a set of files — one upload, or a whole folder tree.

    A folder arrives as a flat list of relative paths, which is what the
    browser's directory picker gives us. Done one-file-at-a-time this would be
    hundreds of round trips and a partially-imported project whenever one of
    them failed; here it is a single transaction that either lands or does not.

    Nothing is overwritten. A path that already exists is reported as skipped
    rather than silently replacing work someone else may be editing.
    """
    if len(body.files) > MAX_IMPORT_FILES:
        raise HTTPException(413,
            f"That folder has {len(body.files)} files. Import at most "
            f"{MAX_IMPORT_FILES} at a time — try a subfolder.")

    total = sum(len((f.content or "").encode("utf-8")) for f in body.files)
    if total > MAX_IMPORT_TOTAL_BYTES:
        raise HTTPException(413,
            f"That's {total // 1_000_000} MB of text; the limit is "
            f"{MAX_IMPORT_TOTAL_BYTES // 1_000_000} MB per import.")

    # Filter first, so an import that turns out to be entirely dependencies
    # does not create an empty project and leave it lying around.
    keep: list[tuple[str, str]] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    for f in body.files:
        raw = (f.path or "").strip().replace("\\", "/").lstrip("/")
        parts = [seg for seg in raw.split("/") if seg not in ("", ".")]
        if not parts or any(seg == ".." for seg in parts) or len("/".join(parts)) > 300:
            skipped.append({"path": raw[:120] or "(unnamed)", "reason": "unusable path"})
            continue
        path = "/".join(parts)
        content = f.content or ""
        reason = import_skip_reason(path, len(content.encode("utf-8")), content)
        if reason:
            skipped.append({"path": path, "reason": reason})
            continue
        if path in seen:
            skipped.append({"path": path, "reason": "duplicate"})
            continue
        seen.add(path)
        keep.append((path, content))

    if not keep:
        raise HTTPException(422,
            "Nothing importable in that selection — it was all dependencies, "
            "build output or binary files.")

    if body.project_id:
        project = _get_project(db, body.project_id)
        existing = {p for (p,) in db.execute(
            select(ProjectFile.path).where(ProjectFile.project_id == project.id))}
        room = MAX_FILES_PER_PROJECT - len(existing)
    else:
        name = (body.name or "Imported").strip()[:120] or "Imported"
        project = Project(name=name, description="Imported from a folder",
                          language=_dominant_language(keep), owner_id=user.id)
        db.add(project)
        db.flush()
        existing, room = set(), MAX_FILES_PER_PROJECT

    added = 0
    for path, content in keep:
        if path in existing:
            skipped.append({"path": path, "reason": "already in this project"})
            continue
        if added >= room:
            skipped.append({"path": path, "reason": f"over the {MAX_FILES_PER_PROJECT}-file limit"})
            continue
        db.add(ProjectFile(project_id=project.id, path=path, language=language_for(path),
                           content=content, size_bytes=len(content.encode("utf-8")),
                           updated_by=user.id))
        added += 1

    if added == 0:
        # Never leave an empty shell behind from a failed import.
        db.rollback()
        raise HTTPException(409, "Every one of those files is already in this project.")

    db.commit()
    db.refresh(project)
    audit.log(db, "project.import", user_id=user.id,
              detail=f"{added} files into '{project.name}' ({len(skipped)} skipped)")
    total_files = db.scalar(select(func.count(ProjectFile.id))
                            .where(ProjectFile.project_id == project.id)) or added
    return {
        "project": _project_out(project, total_files),
        "imported": added,
        "skipped": skipped[:50],          # enough to explain, not enough to flood
        "skipped_total": len(skipped),
    }


def _dominant_language(files: list[tuple[str, str]]) -> str:
    """The language most of the imported files are written in — used as the
    project's label. Ties and all-plaintext both fall back to 'plaintext'."""
    counts: dict[str, int] = {}
    for path, _ in files:
        lang = language_for(path)
        if lang != "plaintext":
            counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else "plaintext"


@router.get("/files/{file_id}")
def read_file(file_id: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    return _file_out(_get_file(db, file_id), with_content=True)


@router.put("/files/{file_id}")
def save_file(file_id: str, body: FileSave, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Explicit save. Snapshots the previous text first, so a collaborative
    session can always be rolled back to a known point."""
    f = _get_file(db, file_id)
    content = body.content or ""
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise HTTPException(413, f"A file is limited to {MAX_FILE_BYTES // 1000} KB.")

    if f.content != content:
        db.add(FileVersion(file_id=f.id, content=f.content, author_id=user.id,
                           author_name=user.full_name, note=body.note.strip()))
        f.content = content
        f.size_bytes = len(content.encode("utf-8"))
        f.updated_by = user.id
        db.commit()
        _trim_versions(db, f.id)
    return _file_out(f, with_content=True)


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: str, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    f = _get_file(db, file_id)
    path = f.path
    db.delete(f)          # versions cascade
    db.commit()
    audit.log(db, "project.file.delete", user.id, path)


# ── versions ─────────────────────────────────────────────────────────────
@router.get("/files/{file_id}/versions")
def list_versions(file_id: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _get_file(db, file_id)
    rows = db.scalars(select(FileVersion)
                      .where(FileVersion.file_id == file_id)
                      .order_by(FileVersion.created_at.desc()).limit(MAX_VERSIONS_KEPT))
    return [{"id": v.id, "author_name": v.author_name, "note": v.note,
             "size": len(v.content), "created_at": v.created_at.isoformat()}
            for v in rows]


@router.post("/files/{file_id}/restore/{version_id}")
def restore_version(file_id: str, version_id: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    f = _get_file(db, file_id)
    v = db.get(FileVersion, version_id)
    if v is None or v.file_id != file_id:
        raise HTTPException(404, "Version not found")
    # Restoring is itself a change worth snapshotting.
    db.add(FileVersion(file_id=f.id, content=f.content, author_id=user.id,
                       author_name=user.full_name, note="before restore"))
    f.content = v.content
    f.size_bytes = len(v.content.encode("utf-8"))
    f.updated_by = user.id
    f.ydoc = None          # CRDT state no longer matches; rebuilt from text
    db.commit()
    audit.log(db, "project.file.restore", user.id, f.path)
    return _file_out(f, with_content=True)


def _trim_versions(db: Session, file_id: str) -> None:
    """Keep history bounded — a busy file would otherwise grow without limit."""
    keep = [v.id for v in db.scalars(
        select(FileVersion).where(FileVersion.file_id == file_id)
        .order_by(FileVersion.created_at.desc()).limit(MAX_VERSIONS_KEPT))]
    if not keep:
        return
    stale = list(db.scalars(select(FileVersion).where(
        FileVersion.file_id == file_id, FileVersion.id.notin_(keep))))
    for v in stale:
        db.delete(v)
    if stale:
        db.commit()


# ── version control ──────────────────────────────────────────────────────
class CommitIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    branch: str = Field(default="main", min_length=1, max_length=80)


class BranchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    from_branch: str = Field(default="main", max_length=80)


def _commit_out(c) -> dict:
    return {"id": c.id, "short": c.id[:8], "branch": c.branch, "message": c.message,
            "author_name": c.author_name, "parent_id": c.parent_id,
            "file_count": c.file_count, "created_at": c.created_at.isoformat()}


@router.get("/{project_id}/status")
def vcs_status(project_id: str, branch: str = Query("main"),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What has changed since the last commit."""
    _get_project(db, project_id)
    return vcs.status(db, project_id, branch)


@router.post("/{project_id}/commits", status_code=201)
def vcs_commit(project_id: str, body: CommitIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    project = _get_project(db, project_id)
    made = vcs.commit(db, project, user, body.message, body.branch)
    if made is None:
        raise HTTPException(409, "Nothing to commit — no files have changed.")
    audit.log(db, "project.commit", user.id, f"{project.name}: {body.message[:80]}")
    return _commit_out(made)


@router.get("/{project_id}/commits")
def vcs_history(project_id: str, branch: str | None = Query(None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_project(db, project_id)
    return [_commit_out(c) for c in vcs.history(db, project_id, branch)]


@router.get("/{project_id}/commits/{commit_id}")
def vcs_commit_detail(project_id: str, commit_id: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """A commit plus the diff it introduced."""
    _get_project(db, project_id)
    c = db.get(Commit, commit_id)
    if c is None or c.project_id != project_id:
        raise HTTPException(404, "Commit not found")
    return {**_commit_out(c), "diff": vcs.diff(db, project_id, c)}


@router.get("/{project_id}/diff")
def vcs_diff(project_id: str, base: str | None = Query(None), head: str | None = Query(None),
             branch: str = Query("main"), db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Diff two commits, or (with neither) the uncommitted working changes."""
    _get_project(db, project_id)
    if head is None:
        return {"kind": "working", "files": vcs.diff_working(db, project_id, branch)}
    to_c = db.get(Commit, head)
    if to_c is None or to_c.project_id != project_id:
        raise HTTPException(404, "Commit not found")
    from_c = None
    if base:
        from_c = db.get(Commit, base)
        if from_c is None or from_c.project_id != project_id:
            raise HTTPException(404, "Base commit not found")
    return {"kind": "commit", "files": vcs.diff(db, project_id, to_c, from_c)}


@router.post("/{project_id}/checkout/{commit_id}")
def vcs_checkout(project_id: str, commit_id: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Restore the working files to a commit. Uncommitted work is auto-saved
    to a rescue branch first, never discarded."""
    project = _get_project(db, project_id)
    c = db.get(Commit, commit_id)
    if c is None or c.project_id != project_id:
        raise HTTPException(404, "Commit not found")
    result = vcs.checkout(db, project, c, user)
    audit.log(db, "project.checkout", user.id, f"{project.name} → {commit_id[:8]}")
    return result


@router.get("/{project_id}/branches")
def vcs_branches(project_id: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    _get_project(db, project_id)
    return vcs.branches(db, project_id)


@router.post("/{project_id}/branches", status_code=201)
def vcs_create_branch(project_id: str, body: BranchIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    project = _get_project(db, project_id)
    made = vcs.create_branch(db, project, user, body.name, body.from_branch)
    if made is None:
        raise HTTPException(409, f"'{body.from_branch}' has no commits to branch from.")
    return _commit_out(made)


# ── AI assistance in the editor ──────────────────────────────────────────
ASSIST_ACTIONS = {
    "explain": ("Explain what this code does",
                "Explain the following code: what it does, how it works, and anything "
                "surprising or risky about it. Be concise and concrete. Do not rewrite it."),
    "fix": ("Find and fix bugs",
            "Review the following code for bugs, edge cases and error handling gaps. "
            "State what is wrong first, then give the corrected code in one fenced block."),
    "test": ("Write tests",
             "Write focused unit tests for the following code. Cover the ordinary path and "
             "the edge cases that would actually break it. Give only the test code, fenced."),
    "document": ("Add documentation",
                 "Add clear docstrings and only genuinely useful comments to the following "
                 "code. Explain why, not what. Return the whole code in one fenced block."),
    "refactor": ("Refactor for clarity",
                 "Refactor the following code for readability without changing its "
                 "behaviour. Say what you changed and why, then give the code fenced."),
}


class AssistIn(BaseModel):
    action: Literal["explain", "fix", "test", "document", "refactor"]
    # The selection, when there is one; otherwise the server uses the whole file.
    selection: str = Field(default="", max_length=20_000)
    question: str = Field(default="", max_length=500)


@router.post("/files/{file_id}/assist")
def assist(file_id: str, body: AssistIn, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """Ask the Coding Agent about this file, or about the selected lines.

    Runs through the same agent, budget ceiling and audit trail as every other
    AI call in the platform — the editor is not a side door around them.
    """
    from app.core.tracing import end_trace, start_trace
    from app.llm import provider
    from app.llm.provider import safe_complete
    from app.services import budget

    f = _get_file(db, file_id)
    budget.check(db, user)             # daily AI spend ceiling, per user

    code = (body.selection or f.content or "").strip()
    if not code:
        raise HTTPException(422, "There is no code to work on yet.")
    if len(code) > 20_000:
        raise HTTPException(413, "Select a smaller portion of the file.")

    _, instruction = ASSIST_ACTIONS[body.action]
    extra = f"\n\nThe developer also asks: {body.question.strip()}" if body.question.strip() else ""
    task = (f"{instruction}{extra}\n\nFile: {f.path} (language: {f.language})\n\n"
            f"```{f.language}\n{code}\n```")

    # Deliberately NOT routed through the Coding Agent's retrieval step. That
    # agent grounds answers in the knowledge base, which is right when someone
    # asks a question about the company's systems — but here the code in front
    # of the developer IS the context, and top-k retrieval over a corpus of
    # contracts and policies only injects noise. (Observed: "explain this
    # function" came back quoting a liability clause.)
    system = (
        "You are the coding assistant inside EAIOS, working in a developer's editor. "
        "Answer only about the code you are given. Be precise and brief. When you "
        "return code, put it in a single fenced block with the correct language tag. "
        "Never invent APIs or behaviour the code does not show."
    )
    start_trace(f"code.{body.action}", user=user.email, kind="chat")
    provider.reset_llm_degraded()
    try:
        answer = safe_complete(system, task)
        end_trace("ok")
    except Exception:
        end_trace("error")
        raise
    audit.log(db, f"code.assist.{body.action}", user.id, f.path)
    return {"action": body.action, "path": f.path, "answer": answer,
            "degraded": provider.llm_degraded()}


@router.get("/assist/actions")
def assist_actions(user: User = Depends(get_current_user)):
    """What the editor's AI menu offers."""
    return [{"id": k, "label": v[0]} for k, v in ASSIST_ACTIONS.items()]
