"""Swapping the starter corpus while it is still being indexed.

Deferring the indexing means a visitor who picks their industry seconds after
opening the demo is deleting rows that a background thread may still be writing
chunks for. That is a real overlap, so these tests exercise it directly.

They also turn foreign keys ON for their own engine. SQLite does not enforce
them by default, which is how a migration that PostgreSQL rejected once shipped
to production green — anything in this file that deletes a parent row is
checked against the constraint production actually applies.

The failure this file was written for turned out to be a window of two
statements wide. ``drop_sample_rows`` deletes chunks, then deletes documents; a
chunk written by the indexer *between* those two statements makes the second
one violate ``chunks_document_id_fkey``, and the visitor sees "a database error
occurred". Threads did not reproduce it reliably — the window is far too narrow
to hit on purpose — so the test below stops trying to win a race and instead
writes the chunk in exactly that window, every time.
"""
import threading

import pytest
from sqlalchemy import event, select

from app.core.database import SessionLocal, engine, init_db
from app.models import Chunk, Document, Organization, User
from app.services import demo, industries


@pytest.fixture
def strict_foreign_keys():
    """Make SQLite behave like the database production actually uses.

    Without this, every delete in this file succeeds regardless of what still
    references it, and the test proves nothing.
    """
    def _on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    event.listen(engine, "connect", _on)
    # existing pooled connections predate the listener
    engine.dispose()
    # These tests never start the app, and the schema is created by its
    # lifespan — so without this they only pass when some other module happens
    # to have run first.
    init_db()
    try:
        yield
    finally:
        event.remove(engine, "connect", _on)
        engine.dispose()


def _demo_workspace() -> tuple[str, str, list]:
    """A demo workspace with its corpus staged but NOT yet indexed."""
    db = SessionLocal()
    try:
        jobs: list = []
        user = demo.start_session(db, defer=jobs)
        # Read them here: the instance detaches when the session closes.
        uid, oid = user.id, user.org_id
        return uid, oid, jobs
    finally:
        db.close()


def test_a_chunk_written_mid_swap_does_not_fail_the_request(strict_foreign_keys):
    """The production failure, made deterministic.

    Rather than start a thread and hope it lands between the two DELETEs, this
    hooks the second one and writes the chunk itself. That is the same state
    the indexer produces, arrived at on purpose: a live child row for a parent
    that is being deleted right now.
    """
    uid, oid, _jobs = _demo_workspace()

    done = {"once": False}

    @event.listens_for(engine, "before_cursor_execute")
    def write_a_chunk_in_the_window(conn, cursor, statement, parameters, context, many):
        if done["once"] or "DELETE FROM documents" not in statement:
            return
        done["once"] = True
        row = cursor.execute(
            "SELECT id, org_id FROM documents WHERE tags LIKE '%sample%' LIMIT 1").fetchone()
        if row is None:                       # nothing to race against
            return
        cursor.execute(
            "INSERT INTO chunks (id, document_id, ord, text, section, page, org_id) "
            "VALUES ('racechunk00000000000000000000000', ?, 0, 'written mid-swap', '', 0, ?)",
            (row[0], row[1]))

    try:
        db = SessionLocal()
        try:
            db.info["org_id"] = oid
            user = db.query(User).filter(User.id == uid).one()
            org = db.get(Organization, oid)
            # Without ON DELETE CASCADE this raises IntegrityError on
            # chunks_document_id_fkey — which is exactly what production did.
            result = industries.apply(db, org, "healthcare", user, defer=True)
            assert result["documents_created"], "the healthcare corpus never arrived"
        finally:
            db.close()
    finally:
        event.remove(engine, "before_cursor_execute", write_a_chunk_in_the_window)

    assert done["once"], "the test never reached the delete it exists to interrupt"

    db = SessionLocal()
    try:
        orphan = db.query(Chunk).filter(
            Chunk.id == "racechunk00000000000000000000000").first()
        assert orphan is None, "the chunk outlived the document it belonged to"
    finally:
        db.close()


def test_foreign_keys_are_actually_enforced_in_this_file(strict_foreign_keys):
    """If this ever stops holding, every other test here becomes decorative."""
    db = SessionLocal()
    try:
        db.execute(select(Document).limit(1))
        enforced = db.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys")).scalar()
        assert enforced == 1, "foreign keys are off; this file cannot catch what it exists to catch"
    finally:
        db.close()


def test_swapping_industry_mid_index_does_not_fail_the_request(strict_foreign_keys):
    """The exact production failure: chunks arriving while the rows are deleted."""
    uid, oid, jobs = _demo_workspace()

    started = threading.Event()
    done = threading.Event()

    def index():
        started.set()
        industries.index_documents(jobs)
        done.set()

    worker = threading.Thread(target=index, daemon=True)
    worker.start()
    started.wait(timeout=5)

    db = SessionLocal()
    try:
        db.info["org_id"] = oid
        user = db.query(User).filter(User.id == uid).one()
        org = db.get(Organization, oid)
        # This is the click. It must not raise, whatever the indexer is doing.
        result = industries.apply(db, org, "healthcare", user, defer=True)
        assert result["documents_created"], "the healthcare corpus never arrived"
    finally:
        db.close()

    worker.join(timeout=30)
    assert done.is_set(), "the background indexer never finished"

    db = SessionLocal()
    try:
        db.info["org_id"] = oid
        titles = {d.title for d in db.query(Document).filter(Document.org_id == oid)}
        assert "Patient Intake Protocol" in titles
        assert "Company Handbook — How We Work" not in titles, "the general pack survived the swap"
    finally:
        db.close()


def test_no_chunks_are_left_pointing_at_a_deleted_document(strict_foreign_keys):
    """An orphaned chunk is invisible to the interface but still retrievable,
    so a swapped-away document would keep turning up in answers."""
    uid, oid, jobs = _demo_workspace()
    industries.index_documents(jobs)          # fully indexed first

    db = SessionLocal()
    try:
        db.info["org_id"] = oid
        user = db.query(User).filter(User.id == uid).one()
        org = db.get(Organization, oid)
        industries.apply(db, org, "legal", user, defer=True)
    finally:
        db.close()

    db = SessionLocal()
    try:
        doc_ids = {d.id for d in db.query(Document).all()}
        orphans = [c.id for c in db.query(Chunk).all() if c.document_id not in doc_ids]
        assert not orphans, f"{len(orphans)} chunk(s) outlived their document"
    finally:
        db.close()


def test_indexing_a_document_that_was_removed_is_not_an_error(strict_foreign_keys):
    """The visitor changed their mind. The job should notice and move on rather
    than marking a row that no longer exists."""
    _, oid, jobs = _demo_workspace()

    db = SessionLocal()
    try:
        db.info["org_id"] = oid
        industries.drop_sample_rows(db)       # as a swap would
    finally:
        db.close()

    industries.index_documents(jobs)          # must not raise

    db = SessionLocal()
    try:
        db.info["org_id"] = oid
        assert db.query(Document).filter(Document.tags.contains("sample")).count() == 0
    finally:
        db.close()
