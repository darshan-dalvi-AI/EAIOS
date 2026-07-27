"""Indexes that outlived their meaning.

``CustomAgent.slug`` and ``Entity.key`` were declared globally UNIQUE when
their tables were first created. Both were later corrected to "unique per
org" — but ``create_all`` never alters an index that already exists, so the
live database went on enforcing globally what is now scoped to one workspace.

The result: the second company to pick an industry hits an integrity error,
because the first company already owns an agent called "protocol-assistant".
Every test passed throughout, because a test database is built fresh from
today's models and never had the old index.

So these tests do the only thing that can catch it — put the old index back,
then check the migration relaxes it.
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


@pytest.mark.parametrize("table,column", [
    ("custom_agents", "slug"),
    ("entities", "key"),
])
def test_a_stale_global_unique_index_is_relaxed_on_boot(own_database, stale_unique_index,
                                                        table, column):
    stale_unique_index(table, column)
    assert _unique_on(own_database, table, column), \
        "the fixture did not reproduce the production state"

    db_module._migrate_add_org_id()          # what init_db runs on every boot

    assert not _unique_on(own_database, table, column), (
        f"{table}.{column} is still globally unique — the second workspace to "
        "use the same value will fail"
    )
    # and the column is still indexed, because these are looked up constantly
    assert any(i.get("column_names") == [column] for i in _indexes(own_database, table)), \
        f"{table}.{column} lost its index entirely"


def test_two_workspaces_can_own_an_agent_with_the_same_slug(own_database, stale_unique_index):
    """The failure as a customer meets it: two companies pick Healthcare."""
    import secrets

    from app.core.security import hash_password
    from app.models import CustomAgent, Organization, User
    from app.services import tenancy

    stale_unique_index("custom_agents", "slug")
    db_module._migrate_add_org_id()

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


def test_the_migration_is_safe_to_run_repeatedly(own_database):
    """It runs on every boot; a second pass must be a no-op rather than an error."""
    db_module._migrate_add_org_id()
    db_module._migrate_add_org_id()
    assert not _unique_on(own_database, "custom_agents", "slug")
