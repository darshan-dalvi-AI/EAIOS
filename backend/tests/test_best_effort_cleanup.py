"""Optional cleanup must not be able to kill the operation around it.

Reported from production: deleting a document from Knowledge returned
"A database error occurred". The delete itself was fine. What broke it was a
*best-effort* step several statements earlier — dropping the document's
extracted `dt_*` tables — written as a bare `try/except: pass`.

On SQLite that is harmless, which is why every test passed. On PostgreSQL a
failed statement aborts the whole transaction, so the swallowed error made
`db.delete(doc)` fail with "current transaction is aborted". The document could
not be deleted at all.

`best_effort` wraps each such step in a SAVEPOINT so a failure rolls back only
that step.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal, best_effort


def test_a_failed_step_does_not_break_the_session():
    """The core guarantee. Without the savepoint this is exactly where the
    production delete died."""
    db = SessionLocal()
    try:
        with best_effort(db, "dropping a table that is not there"):
            db.execute(text('DROP TABLE "dt_definitely_not_here"'))

        # The operation the caller actually cared about must still work.
        assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        db.rollback()
        db.close()


def test_the_exception_is_swallowed_not_raised():
    """These steps are optional: a stale extracted table must never stop
    someone deleting their own document."""
    db = SessionLocal()
    try:
        with best_effort(db, "boom"):
            raise SQLAlchemyError("simulated failure")
        assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        db.rollback()
        db.close()


def test_work_inside_a_successful_block_is_kept():
    """A savepoint that rolled back on success would silently discard the
    cleanup it was supposed to perform."""
    db = SessionLocal()
    try:
        db.execute(text("CREATE TEMPORARY TABLE be_probe (n INTEGER)"))
        with best_effort(db, "insert"):
            db.execute(text("INSERT INTO be_probe (n) VALUES (7)"))
        assert db.execute(text("SELECT n FROM be_probe")).scalar() == 7
    finally:
        db.rollback()
        db.close()


# ── the call sites that must use it ───────────────────────────────────────

@pytest.mark.parametrize("module, function", [
    ("app.api.routes.documents", "delete_document"),
    ("app.services.tenancy", "delete_org"),
])
def test_destructive_paths_use_savepoints_not_bare_except(module, function):
    """Both delete paths run optional cleanup before the real delete. A bare
    `except: pass` in either one reintroduces the production failure — silently,
    because SQLite will not reveal it."""
    import importlib
    import inspect

    src = inspect.getsource(getattr(importlib.import_module(module), function))
    assert "best_effort" in src, f"{function} must scope its cleanup in savepoints"
    # The precise shape that caused the outage.
    assert "except Exception:  # noqa: BLE001\n        pass" not in src
