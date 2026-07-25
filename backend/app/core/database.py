"""SQLAlchemy engine/session. Postgres in production, SQLite fallback in dev.

Pool sizing is load-test informed (Phase 6): the SQLAlchemy default
(pool_size=5, max_overflow=10) exhausts under ~60 concurrent chat requests
and queues connections until timeout. We run a wider pool, and for SQLite
additionally enable WAL + a busy timeout so concurrent readers never block
behind the single writer.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15} if _is_sqlite else {},
    pool_pre_ping=True,
    pool_size=5 if _is_sqlite else 25,   # SQLite: writes serialize anyway; keep it modest
    max_overflow=60,                      # absorb bursts instead of timing out
    pool_timeout=30,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover — exercised implicitly
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")      # readers don't block behind the writer
        cursor.execute("PRAGMA busy_timeout=15000")    # wait for the writer instead of erroring
        cursor.execute("PRAGMA synchronous=NORMAL")    # safe with WAL, much faster
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# ── Multi-tenant isolation ────────────────────────────────────────────────
# Every tenant model mixes in TenantMixin (an ``org_id``). When a request sets
# ``session.info["org_id"]``, these two hooks make isolation automatic:
#   • reads  — a with_loader_criteria on every ORM SELECT adds
#     ``Model.org_id == org_id`` for any TenantMixin entity, so a query can
#     never accidentally return another company's rows.
#   • writes — before flush, new TenantMixin rows are stamped with the org.
# Unauthenticated contexts (login, signup, seeding) leave org_id unset, so the
# filter is skipped and those flows can operate across orgs deliberately.
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import Session as _Session  # noqa: E402
from sqlalchemy.orm import with_loader_criteria  # noqa: E402


def _tenant_mixin():
    from app.models import TenantMixin
    return TenantMixin


@event.listens_for(_Session, "do_orm_execute")
def _scope_reads(state):  # pragma: no cover — exercised via the API tests
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    org_id = state.session.info.get("org_id")
    if not org_id:
        return
    TenantMixin = _tenant_mixin()
    state.statement = state.statement.options(
        with_loader_criteria(TenantMixin, lambda cls: cls.org_id == org_id, include_aliases=True)
    )


@event.listens_for(_Session, "before_flush")
def _stamp_writes(session, _flush_context, _instances):  # pragma: no cover
    org_id = session.info.get("org_id")
    if not org_id:
        return
    from app.models import TenantMixin
    for obj in session.new:
        if isinstance(obj, TenantMixin) and getattr(obj, "org_id", None) is None:
            obj.org_id = org_id


def init_db() -> None:
    # Import models so metadata is populated before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_add_org_id()


def _migrate_add_org_id() -> None:
    """Add the ``org_id`` column to any existing tenant table that predates
    multi-tenancy (create_all only creates missing tables, not columns).
    Idempotent; safe on Postgres and SQLite."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    tenant_tables = [t.name for t in Base.metadata.tables.values() if "org_id" in t.columns]
    with engine.begin() as conn:
        for name in tenant_tables:
            if name not in existing:
                continue
            cols = {c["name"] for c in insp.get_columns(name)}
            if "org_id" not in cols:
                conn.execute(text(f'ALTER TABLE {name} ADD COLUMN org_id VARCHAR(32)'))
