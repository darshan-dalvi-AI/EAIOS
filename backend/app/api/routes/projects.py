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
from app.models import FileVersion, Project, ProjectFile, User
from app.services import audit

router = APIRouter(prefix="/projects", tags=["projects"])

MAX_FILE_BYTES = 512_000        # a source file, not an asset store
MAX_FILES_PER_PROJECT = 200
MAX_VERSIONS_KEPT = 50

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
