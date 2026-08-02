import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core import storage, uploads
from app.core.config import settings
from app.core.database import best_effort
from app.models import Chunk, Document, Organization, User
from app.rag import pipeline
from app.schemas import ChunkOut, DocumentOut
from app.services import audit, plans

router = APIRouter(prefix="/documents", tags=["documents"])

EXT_MAP = {
    ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx",
    ".csv": "csv", ".txt": "txt", ".md": "txt",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
}


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload(
    file: UploadFile,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # The caller's filename is a claim: sanitise it, check the extension is
    # one we accept, then verify the *content* matches while streaming under
    # a hard size cap (see core/uploads.py).
    safe_name = uploads.safe_filename(file.filename)
    ext, doc_type = uploads.check_extension(safe_name)

    # Checked before a byte is written, so a workspace at its allowance is told
    # immediately rather than after uploading a large file.
    plans.enforce(db, db.get(Organization, user.org_id) if user.org_id else None, "documents")

    doc = Document(
        filename=safe_name,
        title=os.path.splitext(safe_name)[0].replace("_", " ").replace("-", " ").title()[:255],
        doc_type=doc_type,
        owner_id=user.id,
        status="queued",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    upload_dir = uploads.ensure_upload_dir()
    dest = os.path.join(upload_dir, f"{doc.id}{ext}")
    try:
        doc.size_bytes = uploads.stream_to_disk(file.file, dest, ext)
    except Exception:
        # Never leave an orphan row behind for a file we refused to store.
        db.delete(doc)
        db.commit()
        raise
    db.commit()

    tasks.add_task(pipeline.ingest_document, doc.id, dest)
    tasks.add_task(storage.put, f"{doc.id}{ext}", dest)  # mirror to Supabase Storage (no-op if unset)
    audit.log(db, "document.upload", user.id, file.filename or "")
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # Bounded by default — a mature workspace can hold thousands of documents,
    # and returning all of them in one unpaginated payload grows without limit.
    return list(db.scalars(
        select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)))


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def document_chunks(doc_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Document, doc_id) is None:
        raise HTTPException(404, "Document not found")
    return db.scalars(select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.ord)).all()


@router.post("/{doc_id}/reindex", response_model=DocumentOut)
def reindex(doc_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    stored = _stored_path(doc)
    if stored is None:
        raise HTTPException(409, "Original file no longer on disk")
    doc.status = "queued"
    db.commit()
    tasks.add_task(pipeline.ingest_document, doc.id, stored)
    return doc


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if user.role != "admin" and doc.owner_id != user.id:
        raise HTTPException(403, "Only the owner or an admin can delete this document")
    pipeline.delete_document_vectors(doc_id)

    # Each cleanup gets its own SAVEPOINT. These are best-effort — a stale
    # extracted table or an orphaned entity must not stop someone deleting
    # their own document — but "best effort" used to mean `except: pass`, and
    # on PostgreSQL that poisons the transaction: the swallowed error made
    # every later statement fail, so `db.delete(doc)` below returned
    # "A database error occurred" and the document could never be removed.
    # SQLite does not behave that way, which is why the tests were green.
    with best_effort(db, "dropping extracted tables"):
        from app.rag import tables as dtables

        dtables.drop_for_document(db, doc_id)

    with best_effort(db, "forgetting graph entities"):
        from app.services import kgraph

        kgraph.forget_document(db, doc_id)

    with best_effort(db, "removing the stored file"):
        ext = os.path.splitext(doc.filename)[1].lower()
        storage.remove(f"{doc.id}{ext}")  # deletes local + Supabase copy

    db.delete(doc)
    db.commit()
    audit.log(db, "document.delete", user.id, doc.filename)


def _stored_path(doc: Document) -> str | None:
    """Local path to the original file, re-fetched from Supabase Storage if the
    container's cache is cold (e.g. after a redeploy)."""
    ext = os.path.splitext(doc.filename)[1].lower()
    return storage.ensure_local(f"{doc.id}{ext}")


# ── analyzer quick-actions (Resume / Contract / Invoice / Auto) ──────────
from pydantic import BaseModel, Field  # noqa: E402


class AnalyzeIn(BaseModel):
    kind: str = Field(default="auto", pattern="^(resume|contract|invoice|auto)$")


@router.post("/{doc_id}/analyze")
def analyze(doc_id: str, body: AnalyzeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Structured scorecard for an indexed document — templated analyst
    prompts over its chunks + extracted SQL tables, with a deterministic
    heuristic fallback so demo mode always answers."""
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if doc.status != "indexed":
        raise HTTPException(409, f"Document is not indexed yet (status: {doc.status})")

    from app.services import analyze as analyzer

    result = analyzer.analyze_document(db, doc, body.kind)
    audit.log(db, "document.analyze", user.id, f"{doc.filename} kind={body.kind} engine={result.get('engine')}")
    return {"doc_id": doc.id, "title": doc.title, **result}
