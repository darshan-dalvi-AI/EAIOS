"""The migrations have to run on the database production actually uses.

The suite runs on SQLite; the deployment runs on PostgreSQL. SQLite is the
more forgiving of the two, so a migration can pass every test here and still
abort startup in production — which is exactly what happened:

    ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0

SQLite stores booleans as integers and accepts it. PostgreSQL rejects it
("column ... is of type boolean but default expression is of type integer"),
the exception escapes the migration transaction, FastAPI's lifespan fails, and
uvicorn exits with status 3 — the whole service, not just the new feature.

These tests read the DDL rather than execute it, because the failure is a
dialect difference no SQLite run can reproduce.
"""
import re
from pathlib import Path

import pytest

from app.core import database

SOURCE = Path(database.__file__).read_text(encoding="utf-8")

# Values PostgreSQL accepts for a boolean. 0 and 1 are conspicuously absent.
BOOL_LITERALS = {"TRUE", "FALSE", "NULL"}


@pytest.mark.parametrize("column,ddl", database.USER_VERIFY_COLUMNS)
def test_boolean_columns_default_to_a_boolean_literal(column, ddl):
    if "BOOLEAN" not in ddl.upper():
        pytest.skip(f"{column} is not a boolean column")
    default = re.search(r"DEFAULT\s+(\S+)", ddl, re.I)
    assert default, f"{column} should state a default so existing rows are not NULL"
    assert default.group(1).upper() in BOOL_LITERALS, (
        f"{column} defaults to {default.group(1)!r}; PostgreSQL will refuse an "
        f"integer default on a boolean column and startup will fail"
    )


def test_the_ddl_names_the_column_it_is_keyed_by():
    """A mismatch would silently re-add a column on every boot."""
    for column, ddl in database.USER_VERIFY_COLUMNS:
        assert ddl.split()[0] == column, f"{column!r} is keyed to DDL for {ddl.split()[0]!r}"


def test_no_migration_assigns_an_integer_to_a_boolean_column():
    """`UPDATE users SET email_verified = 1` is the same mistake in UPDATE form."""
    bool_columns = {c for c, ddl in database.USER_VERIFY_COLUMNS if "BOOLEAN" in ddl.upper()}
    offenders = [
        m.group(0)
        for m in re.finditer(r"SET\s+(\w+)\s*=\s*([01])\b", SOURCE, re.I)
        if m.group(1) in bool_columns
    ]
    assert not offenders, f"assign TRUE/FALSE, not 0/1: {offenders}"


def test_migrations_are_idempotent_by_construction():
    """Every ADD COLUMN is guarded by a check that the column is missing —
    without it, the second boot crashes on 'column already exists'."""
    assert 'if col not in ucols:' in SOURCE
    assert 'if "org_id" not in cols:' in SOURCE


def test_the_migration_runs_clean_on_a_database_that_predates_it(tmp_path):
    """A schema from before verification existed, migrated forward."""
    from sqlalchemy import create_engine, inspect, text

    db = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        # the `users` table as it looked before this feature
        conn.execute(text("CREATE TABLE users (id VARCHAR(32) PRIMARY KEY, email VARCHAR(200), "
                          "org_id VARCHAR(32))"))
        conn.execute(text("INSERT INTO users (id, email) VALUES ('u1', 'old@customer.dev')"))

    original = database.engine
    try:
        database.engine = engine
        database._migrate_add_org_id()
    finally:
        database.engine = original

    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {c for c, _ in database.USER_VERIFY_COLUMNS} <= cols

    with engine.connect() as conn:
        verified = conn.execute(text("SELECT email_verified FROM users WHERE id = 'u1'")).scalar()
    # Grandfathered: a customer who signed up before the gate existed is not
    # locked out of their own workspace by it.
    assert bool(verified) is True
