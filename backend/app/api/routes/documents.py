import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core import storage
from app.core.config import settings
from app.models import Chunk, Document, User
from app.rag import pipeline
from app.schemas import ChunkOut, DocumentOut
from app.services import audit

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
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXT_MAP:
        raise HTTPException(415, f"Unsupported type '{ext}'. Allowed: {', '.join(sorted(EXT_MAP))}")

    doc = Document(
        filename=file.filename or "upload",
        title=os.path.splitext(file.filename or "upload")[0].replace("_", " ").replace("-", " ").title(),
        doc_type=EXT_MAP[ext],
        owner_id=user.id,
        status="queued",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(settings.UPLOAD_DIR, f"{doc.id}{ext}")
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    doc.size_bytes = os.path.getsize(dest)
    db.commit()

    tasks.add_task(pipeline.ingest_document, doc.id, dest)
    tasks.add_task(storage.put, f"{doc.id}{ext}", dest)  # mirror to Supabase Storage (no-op if unset)
    audit.log(db, "document.upload", user.id, file.filename or "")
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Document).order_by(Document.created_at.desc())).all()


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
    try:  # drop structured tables materialized from this document
        from app.rag import tables as dtables

        dtables.drop_for_document(db, doc_id)
    except Exception:  # noqa: BLE001
        pass
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
