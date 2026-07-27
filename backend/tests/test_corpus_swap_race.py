"""Swapping the starter corpus while it is still being indexed.

Deferring the indexing means a visitor who picks their industry seconds after
opening the demo is deleting rows that a background thread may still be writing
chunks for. That is a real overlap, so these tests exercise it directly.

They also turn foreign keys ON for their own engine. SQLite does not enforce
them by default, which is how a migration that PostgreSQL rejected once shipped
to production green — anything in this file that deletes a parent row is
checked against the constraint production actually applies.

An honest caveat: this file did **not** reproduce the "a database error
occurred" seen live after the deferral change. Reproducing that flow against a
real PostgreSQL instance — including the deployed commit — came back clean, so
the cause lies somewhere these tests do not reach (most likely contention with
the boot-time schema hardening, which takes exclusive table locks for about a
minute after every deploy). These tests are kept because the properties they
assert are worth holding, not because they caught that.
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
