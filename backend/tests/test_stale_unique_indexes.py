"""Uniqueness that outlived its meaning.

``CustomAgent.slug`` and ``Entity.key`` were declared globally UNIQUE when
their tables were first created. Both were later corrected to "unique per
org" — but ``create_all`` never alters an index that already exists, so the
live database went on enforcing globally what is now scoped to one workspace.

The result: the second company to pick an industry hits an integrity error,
because the first company already owns an agent called "protocol-assistant".
Every test passed throughout, because a test database is built fresh from
today's models and never had the old index.

So these tests do the only thing that can catch it — put the old uniqueness
back, then check the repair removes it. They cover both shapes it can take,
a UNIQUE INDEX and a UNIQUE CONSTRAINT, because PostgreSQL reports those
separately and they need different DDL to remove.
"""
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core import database as db_module


@pytest.fixture(autouse=True)
def own_database(monkeypatch):
    """A database of this file's own, built the way production's was.

    The rest of the suite shares one database and fills it with workspaces —
    several of which legitimately own an agent called "protocol-assistant".
    A UNIQUE index cannot even be created over that, so the fixture below could
    not reproduce the production state while sharing it.
    """
    from app import models  # noqa: F401 — populates the metadata create_all reads

    path = Path(tempfile.mkdtemp()) / "stale.db"
    eng = create_engine(f"sqlite:///{path.as_posix()}",
                        connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=eng, autoflush=False))
    db_module.Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


def _indexes(eng, table: str) -> list[dict]:
    return inspect(eng).get_indexes(table)


def _unique_on(eng, table: str, column: str) -> bool:
    return any(i.get("unique") and i.get("column_names") == [column]
               for i in _indexes(eng, table))


@pytest.fixture
def stale_unique_index(own_database):
    """Recreate the database as it exists in production: a global unique index
    on a column that is only supposed to be unique within a workspace."""
    def make(table: str, column: str) -> None:
        with own_database.begin() as conn:
            conn.execute(text(f'DROP INDEX IF EXISTS "ix_{table}_{column}"'))
            conn.execute(text(
                f'CREATE UNIQUE INDEX "ix_{table}_{column}" ON {table} ("{column}")'))

    return make


# ── what the database still enforces, and what the models say ───────────────

@pytest.mark.parametrize("table,column", [
    ("custom_agents", "slug"),
    ("entities", "key"),
])
def test_drift_is_detected(own_database, stale_unique_index, table, column):
    assert db_module.stale_global_uniques() == [], "a fresh database has not drifted"

    stale_unique_index(table, column)

    drift = db_module.stale_global_uniques()
    assert {(d["table"], d["column"]) for d in drift} == {(table, column)}, drift


def test_columns_that_are_still_globally_unique_are_left_alone(own_database):
    """The repair is derived from the models, so it must not overreach.

    An account is one-per-address and a workspace is one-per-slug; both are
    *meant* to be globally unique. Sweeping "every unique index" would quietly
    let two people register the same email.
    """
    assert _unique_on(own_database, "users", "email")
    assert _unique_on(own_database, "organizations", "slug")

    db_module.relax_stale_global_uniques()

    assert _unique_on(own_database, "users", "email"), \
        "two accounts could now share an email address"
    assert _unique_on(own_database, "organizations", "slug"), \
        "two workspaces could now share a slug"


# ── the repair ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("table,column", [
    ("custom_agents", "slug"),
    ("entities", "key"),
])
def test_a_stale_global_unique_index_is_relaxed_on_boot(own_database, stale_unique_index,
                                                        table, column):
    stale_unique_index(table, column)
    assert _unique_on(own_database, table, column), \
        "the fixture did not reproduce the production state"

    repaired = db_module.relax_stale_global_uniques()   # what init_db runs on every boot

    assert f"{table}.{column}" in repaired
    assert not _unique_on(own_database, table, column), (
        f"{table}.{column} is still globally unique — the second workspace to "
        "use the same value will fail"
    )
    # and the column is still indexed, because these are looked up constantly
    assert any(i.get("column_names") == [column] for i in _indexes(own_database, table)), \
        f"{table}.{column} lost its index entirely"


def test_drift_shaped_as_a_constraint_is_detected(own_database):
    """The same drift, in the shape PostgreSQL reports separately.

    ``get_indexes`` omits an index that backs a UNIQUE *constraint*, and
    ``DROP INDEX`` cannot remove one. A repair that only knew about indexes
    would report success having changed nothing — indistinguishable, from
    outside, from the migration never running at all.

    Detection is asserted here; the ``ALTER TABLE ... DROP CONSTRAINT`` half
    cannot be, because SQLite has no way to drop a constraint. That half is
    covered against a real PostgreSQL built from the old models.
    """
    # Rebuild `entities` exactly as it is, plus the constraint the old models
    # would have produced. Taking the DDL from the database keeps every column
    # and foreign key intact.
    with own_database.begin() as conn:
        ddl = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entities'")).scalar()
        conn.execute(text("DROP TABLE entities"))
        cut = ddl.rstrip().rfind(")")
        conn.execute(text(
            ddl[:cut] + ', CONSTRAINT uq_entities_key UNIQUE ("key")' + ddl[cut:]))

    assert any(c["column_names"] == ["key"]
               for c in inspect(own_database).get_unique_constraints("entities")), \
        "the fixture did not reproduce a constraint-shaped unique"

    drift = db_module.stale_global_uniques()
    assert {(d["column"], d["kind"]) for d in drift} == {("key", "constraint")}, drift


def test_the_repair_is_safe_to_run_repeatedly(own_database, stale_unique_index):
    """It runs on every boot; a second pass must be a no-op rather than an error."""
    stale_unique_index("custom_agents", "slug")

    assert db_module.relax_stale_global_uniques() == ["custom_agents.slug"]
    assert db_module.relax_stale_global_uniques() == [], "the second pass repaired something again"
    assert not _unique_on(own_database, "custom_agents", "slug")


def test_one_stubborn_index_does_not_block_the_others(own_database, stale_unique_index,
                                                      monkeypatch):
    """Each repair runs in its own transaction.

    On PostgreSQL a failed statement aborts the whole transaction: everything
    after it fails too, and the commit silently becomes a rollback. Sharing one
    transaction would let a single awkward index undo every repair before it.
    """
    stale_unique_index("custom_agents", "slug")
    stale_unique_index("entities", "key")

    real = db_module.stale_global_uniques

    def with_a_bad_one():
        return [{"table": "no_such_table", "column": "x",
                 "name": "ix_no_such_table_x", "kind": "constraint"}] + real()

    monkeypatch.setattr(db_module, "stale_global_uniques", with_a_bad_one)

    repaired = db_module.relax_stale_global_uniques()

    assert set(repaired) == {"custom_agents.slug", "entities.key"}, \
        "a failure on an unrelated table took the real repairs down with it"


# ── the failure as a customer meets it ──────────────────────────────────────

def test_two_workspaces_can_own_an_agent_with_the_same_slug(own_database, stale_unique_index):
    """Two companies pick Healthcare. Both must get their agents."""
    import secrets

    from app.core.security import hash_password
    from app.models import CustomAgent, Organization, User
    from app.services import tenancy

    stale_unique_index("custom_agents", "slug")
    db_module.relax_stale_global_uniques()

    db = db_module.SessionLocal()
    try:
        for name in ("First Clinic", "Second Clinic"):
            org: Organization = tenancy.create_org(db, name)
            owner = User(email=f"owner-{secrets.token_hex(4)}@clinic.dev",
                         full_name="Owner", hashed_password=hash_password("x"),
                         role="admin", org_id=org.id)
            db.add(owner)
            db.flush()
            db.add(CustomAgent(
                slug="protocol-assistant", name="Protocol Assistant",
                description="", system_prompt="", tools="[]", hue=350,
                owner_id=owner.id, org_id=org.id,
            ))
        db.commit()          # this is what raised in production

        rows = db.query(CustomAgent).filter(CustomAgent.slug == "protocol-assistant").all()
        assert len({r.org_id for r in rows}) >= 2, "the two workspaces did not both get one"

        for row in rows:
            db.delete(row)
        db.commit()
    finally:
        db.close()
