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
    # NOTE: harden_public_schema() is deliberately NOT called here. It issues
    # ~60 statements against a database that may be in another region, which
    # delayed the first health check enough to fail a deploy. main.py runs it
    # in the background once the app is already serving.


# ── Supabase / Postgres surface hardening ─────────────────────────────────
# Supabase auto-publishes EVERY table in the `public` schema through its
# PostgREST API, reachable with the project's anon key. EAIOS never uses that
# API — it talks to Postgres directly over SQLAlchemy — so the whole REST
# surface should be shut, not merely policed. Two independent locks:
#
#   1. ENABLE ROW LEVEL SECURITY with **no policies** → deny-by-default for
#      every API role. (The app is unaffected: it connects as the table owner,
#      and owners/BYPASSRLS roles are not subject to RLS unless FORCE is set.)
#   2. REVOKE the table grants Supabase hands to `anon`/`authenticated`, and
#      revoke them from DEFAULT PRIVILEGES so tables created later — including
#      the dynamic ``dt_*`` tables built from uploaded spreadsheets — are never
#      exposed in the first place.
#
# Idempotent, Postgres-only (no-op on SQLite), and never fatal: a permission
# error here must not stop the app from booting.
_API_ROLES = ("anon", "authenticated")


def harden_public_schema(only_table: str | None = None) -> None:
    """Close the Supabase REST surface for public tables. See module notes."""
    if _is_sqlite:
        return

    import logging

    from sqlalchemy import text

    log = logging.getLogger("eaios")
    try:
        with engine.begin() as conn:
            roles = [
                r for r in _API_ROLES
                if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": r}).first()
            ]

            if only_table:
                tables = [only_table]
            else:
                tables = [
                    row[0] for row in conn.execute(text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                    ))
                ]

            secured = 0
            for name in tables:
                ident = f'public."{name}"'
                try:
                    conn.execute(text(f"ALTER TABLE {ident} ENABLE ROW LEVEL SECURITY"))
                    for role in roles:
                        conn.execute(text(f"REVOKE ALL ON {ident} FROM {role}"))
                    secured += 1
                except Exception as exc:  # noqa: BLE001 — one bad table must not stop the rest
                    log.warning("RLS hardening skipped for %s: %s", name, exc)

            # Future tables (dt_* materialised at runtime, new models) inherit
            # no API grants at all.
            for role in roles:
                try:
                    conn.execute(text(
                        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role}"
                    ))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Default-privilege revoke failed for %s: %s", role, exc)

        if secured:
            log.info("Public schema hardened: RLS on %d table(s), API roles revoked %s",
                     secured, roles or "(none present)")
    except Exception as exc:  # noqa: BLE001 — hardening must never block startup
        log.warning("Public schema hardening skipped: %s", exc)


# Columns added to `users` when email verification shipped.
#
# The literals matter: SQLite accepts 0/1 for a BOOLEAN, PostgreSQL does not
# ("column is of type boolean but default expression is of type integer"), and
# it raises inside the migration transaction — which fails startup and takes
# the whole service down. The suite runs on SQLite, so it happily accepted a
# statement production rejected. `TRUE`/`FALSE` are valid on both.
USER_VERIFY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("email_verified", "email_verified BOOLEAN DEFAULT FALSE"),
    ("auth_provider", "auth_provider VARCHAR(20) DEFAULT 'password'"),
    ("verify_code_hash", "verify_code_hash VARCHAR(200)"),
    ("verify_expires_at", "verify_expires_at TIMESTAMP"),
    ("verify_attempts", "verify_attempts INTEGER DEFAULT 0"),
)


def _migrate_add_org_id() -> None:
    """Add the ``org_id`` column to any existing tenant table that predates
    multi-tenancy (create_all only creates missing tables, not columns).
    Idempotent; safe on Postgres and SQLite."""
    import logging

    from sqlalchemy import inspect, text

    log = logging.getLogger("eaios")
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

        # Users gained email-verification columns after the first release.
        if "users" in existing:
            ucols = {c["name"] for c in insp.get_columns("users")}
            for col, ddl in USER_VERIFY_COLUMNS:
                if col not in ucols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {ddl}"))
            # Accounts that existed before verification was introduced keep
            # working — retro-locking real customers out would be worse than
            # the gap it closes. New signups are gated from here on.
            if "email_verified" not in ucols:
                conn.execute(text("UPDATE users SET email_verified = TRUE"))

        # ── indexes that outlived their meaning ──────────────────────────
        # These two columns were declared globally UNIQUE when their tables
        # were first created, and were later corrected to "unique per org".
        # ``create_all`` only creates missing tables — it never alters an index
        # that already exists. So a database created before the correction goes
        # on enforcing globally what is now supposed to be scoped to a single
        # workspace: the second company to name an agent "protocol-assistant",
        # or to mention an entity another company already mentions, gets an
        # integrity error and a failed request.
        #
        # A database created from today's models has no such index, which is
        # exactly why this was invisible in development and in every test, and
        # only appeared once two workspaces on the live deployment picked the
        # same industry.
        for table, column in (("custom_agents", "slug"), ("entities", "key")):
            if table not in existing:
                continue
            for index in insp.get_indexes(table):
                if not index.get("unique") or index.get("column_names") != [column]:
                    continue
                name = index.get("name")
                try:
                    conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                    conn.execute(text(
                        f'CREATE INDEX IF NOT EXISTS "ix_{table}_{column}" ON {table} ("{column}")'))
                    log.info("dropped stale global unique index %s (now per-tenant)", name)
                except Exception as exc:   # noqa: BLE001 — a constraint may need different DDL
                    log.warning("could not relax unique index %s: %s", name, exc)

        # The audit trail gained the actor's address so an entry still names a
        # person after that person is removed from the workspace.
        if "audit_logs" in existing:
            audit_cols = {c["name"] for c in insp.get_columns("audit_logs")}
            if "actor_email" not in audit_cols:
                conn.execute(text(
                    "ALTER TABLE audit_logs ADD COLUMN actor_email VARCHAR(200) DEFAULT ''"))

        # Organizations gained `status` after the first multi-tenant release.
        if "organizations" in existing:
            org_cols = {c["name"] for c in insp.get_columns("organizations")}
            if "industry" not in org_cols:
                conn.execute(text(
                    "ALTER TABLE organizations ADD COLUMN industry VARCHAR(40) DEFAULT ''"))
            # Throwaway workspaces handed to visitors trying the product.
            if "is_demo" not in org_cols:
                conn.execute(text(
                    "ALTER TABLE organizations ADD COLUMN is_demo BOOLEAN DEFAULT FALSE"))
            if "expires_at" not in org_cols:
                conn.execute(text(
                    "ALTER TABLE organizations ADD COLUMN expires_at TIMESTAMP"))
            if "status" not in org_cols:
                conn.execute(text(
                    "ALTER TABLE organizations ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                conn.execute(text("UPDATE organizations SET status = 'active' WHERE status IS NULL"))

    _backfill_null_orgs(existing, tenant_tables)


def _backfill_null_orgs(existing: set[str], tenant_tables: list[str]) -> None:
    """Adopt pre-multi-tenancy rows into the default demo workspace.

    SECURITY: a row with ``org_id IS NULL`` belongs to no workspace, and a
    *user* with no org gets no read filter at all (the hook skips when the
    session has no org) — so a legacy account could see every company's data.
    Any row that predates multi-tenancy is therefore adopted by the default
    demo org, which restores the invariant "every row has exactly one owner".
    """
    from sqlalchemy import text

    if "organizations" not in existing or "users" not in existing:
        return
    try:
        from app.services.tenancy import DEFAULT_SLUG

        with engine.begin() as conn:
            orphans = conn.execute(text("SELECT COUNT(*) FROM users WHERE org_id IS NULL")).scalar()
            if not orphans:
                return
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE slug = :s"), {"s": DEFAULT_SLUG}).scalar()
            if not org_id:
                import uuid
                org_id = uuid.uuid4().hex[:32]
                conn.execute(
                    text("INSERT INTO organizations (id, name, slug, plan, status, created_at) "
                         "VALUES (:i, :n, :s, 'free', 'active', CURRENT_TIMESTAMP)"),
                    {"i": org_id, "n": "EAIOS Demo Workspace", "s": DEFAULT_SLUG})
            for name in tenant_tables:
                if name in existing:
                    conn.execute(text(f"UPDATE {name} SET org_id = :o WHERE org_id IS NULL"),
                                 {"o": org_id})
        import logging
        logging.getLogger("eaios").info(
            "Adopted %d pre-tenancy user(s) and their data into the default workspace", orphans)
    except Exception as exc:  # noqa: BLE001 — never block startup
        import logging
        logging.getLogger("eaios").warning("org backfill skipped: %s", exc)
