"""Ingestion pipeline: parse → chunk → embed → index.
Runs as a FastAPI background task; swap in Celery for heavy production loads."""
import logging

from app.core.database import SessionLocal
from app.core.events import hub
from app.models import Chunk, Document
from app.rag.chunking import chunk_blocks
from app.rag.embeddings import embed_texts
from app.rag.parsers import parse_file
from app.rag.vectorstore import get_vectorstore

log = logging.getLogger("eaios.pipeline")


def ingest_document(doc_id: str, path: str) -> None:
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        doc.status = "processing"
        db.commit()

        try:
            blocks = parse_file(path, doc.doc_type)

            # advanced parsing: complex/nested tables → REAL SQL tables the
            # SQL Agent can query; each returns a summary block for the index
            table_blocks: list = []
            try:
                from app.rag import tables as dtables

                table_blocks = dtables.ingest_tables(db, doc, path)
            except Exception:  # noqa: BLE001 — structured extraction never blocks indexing
                log.exception("table materialization failed for %s", doc_id)
            blocks = blocks + table_blocks

            chunks = chunk_blocks(blocks)

            # Replace any previous index for this document
            db.query(Chunk).filter(Chunk.document_id == doc_id).delete()
            get_vectorstore().delete_document(doc_id)

            records = [
                Chunk(document_id=doc_id, ord=i, text=c["text"], section=c["section"], page=c["page"])
                for i, c in enumerate(chunks)
            ]
            db.add_all(records)
            db.flush()  # assign IDs before embedding upsert

            vectors = embed_texts([c.text for c in records])
            get_vectorstore().upsert(
                ids=[c.id for c in records],
                vectors=vectors,
                payloads=[
                    {"doc_id": doc_id, "section": c.section, "page": c.page, "preview": c.text[:160]}
                    for c in records
                ],
            )

            # knowledge graph: extract entities + co-occurrence edges
            try:
                from app.services import kgraph

                entities = kgraph.index_chunks(db, doc, records)
            except Exception:  # noqa: BLE001 — graph is additive, never blocks indexing
                log.exception("entity extraction failed for %s", doc_id)
                entities = 0

            doc.status = "indexed"
            doc.chunk_count = len(records)
            doc.page_count = max((c.page for c in records), default=0)
            doc.error = None
            db.commit()
            log.info("Indexed %s → %d chunks, %d entities, %d structured table(s)",
                     doc.filename, len(records), entities, len(table_blocks))
            hub.publish("doc.status", doc_id=doc.id, title=doc.title, status="indexed",
                        chunks=len(records), entities=entities, tables=len(table_blocks))

            # fire upload-triggered automations (workflow engine)
            try:
                from app.services import workflows

                workflows.fire_trigger(db, "upload", f"Document '{doc.title}' ({doc.filename}) was indexed "
                                                     f"with {len(records)} chunks.")
            except Exception:  # noqa: BLE001
                log.exception("upload trigger failed for %s", doc_id)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            doc = db.get(Document, doc_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = str(exc)[:500]
                db.commit()
            log.exception("Ingestion failed for %s", doc_id)


def delete_document_vectors(doc_id: str) -> None:
    get_vectorstore().delete_document(doc_id)
