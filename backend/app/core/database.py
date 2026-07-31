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


_migrated_urls: set[str] = set()


def init_db() -> None:
    # Import models so metadata is populated before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # The schema-reconciling migrations below each inspect every table, which is
    # a real cost (dozens of round trips) and pointless to repeat: a database's
    # shape does not change under us within one process. Production calls init_db
    # once at boot, so it always runs; a test harness that spins the app up many
    # times against the same database runs them once and then skips — the runs
    # are idempotent, so skipping an already-reconciled database changes nothing.
    url = str(engine.url)
    if url in _migrated_urls:
        return
    _migrate_add_org_id()
    # Outside the migration's transaction, deliberately: see the note there.
    relax_stale_global_uniques()
    add_missing_cascades()
    create_missing_indexes()
    harden_column_types_and_checks()
    _migrated_urls.add(url)
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


# ── Row-Level-Security backstop for the SQL agent ─────────────────────────────
# The SQL agent runs model-generated SQL. A regex guard rewrites it to stay in
# one workspace (agents/sql_agent.py), and that guard is the first line — but a
# regex can never enumerate every lexical form Postgres accepts (a
# schema-qualified name once slipped past it and leaked across tenants). So the
# database itself becomes the second, unbypassable line:
#
#   * ``eaios_restricted`` — a NOLOGIN role the agent's query runs *as*. It is
#     neither a table owner nor BYPASSRLS, so Row-Level Security applies to it.
#   * A policy on every ``org_id`` table: a row is visible only when its
#     ``org_id`` equals ``current_setting('eaios.org_id')``, which the agent sets
#     to the caller's workspace for the duration of that one query.
#
# The upshot: even a query the regex guard fails to scope returns only the
# caller's rows, because the role executing it can physically see nothing else.
# ``organizations`` (the tenant registry, no org_id) gets no policy at all, so
# the role can't read it. ``dt_*`` extracted tables have no org_id and are
# already scoped by the guard's ownership allowlist, so they get a permissive
# policy — the guard remains their control; RLS is the backstop for the rest.
#
# Idempotent, Postgres-only, never fatal. If it can't be set up (no permission,
# SQLite), the agent simply keeps using the regex guard alone, as before.
_rls_ready = False


def rls_enabled() -> bool:
    """Whether the SQL agent can run its query under the restricted RLS role."""
    return _rls_ready and not _is_sqlite


def setup_sql_agent_rls(only_table: str | None = None) -> bool:
    """Create/refresh the restricted role and its per-table policies."""
    global _rls_ready
    if _is_sqlite:
        return False

    import logging

    from sqlalchemy import text

    log = logging.getLogger("eaios")
    tenant_tables = {t.name for t in Base.metadata.tables.values() if "org_id" in t.columns}

    # The role + schema-wide grants, in their own transaction. Everything after
    # gets its OWN transaction per table: on Postgres one failed statement
    # aborts the whole transaction it's in, so a single awkward table sharing a
    # transaction with the role setup would silently undo the role too.
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='eaios_restricted') "
                "THEN CREATE ROLE eaios_restricted NOLOGIN; END IF; END $$;"))
            conn.execute(text("GRANT USAGE ON SCHEMA public TO eaios_restricted"))
            conn.execute(text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO eaios_restricted"))
    except Exception as exc:  # noqa: BLE001 — never block startup; agent falls back to the guard
        log.warning("SQL-agent RLS role unavailable (regex guard still active): %s", exc)
        return False

    if only_table:
        names = [only_table]
    else:
        try:
            with engine.connect() as conn:
                names = [row[0] for row in conn.execute(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))]
        except Exception:  # noqa: BLE001
            names = list(tenant_tables)

    covered = 0
    for name in names:
        is_tenant = name in tenant_tables
        if not (is_tenant or name.startswith("dt_")):
            continue  # e.g. organizations — RLS with no policy hides it entirely
        ident = f'public."{name}"'
        using = ("org_id::text = current_setting('eaios.org_id', true)" if is_tenant else "true")
        try:
            with engine.begin() as conn:      # its own transaction, per table
                conn.execute(text(f"GRANT SELECT ON {ident} TO eaios_restricted"))
                conn.execute(text(f"ALTER TABLE {ident} ENABLE ROW LEVEL SECURITY"))
                conn.execute(text(f'DROP POLICY IF EXISTS eaios_agent_read ON {ident}'))
                conn.execute(text(
                    f"CREATE POLICY eaios_agent_read ON {ident} "
                    f"FOR SELECT TO eaios_restricted USING ({using})"))
            covered += 1
        except Exception as exc:  # noqa: BLE001 — one table must not stop the rest
            log.warning("RLS policy skipped for %s: %s", name, exc)

    if not only_table:
        log.info("SQL-agent RLS backstop ready: eaios_restricted + policies on %d table(s)", covered)
    _rls_ready = True
    return True


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
    # Server-side token revocation epoch (logout / sign-out-everywhere).
    # Double precision: it holds a sub-second timestamp, matching the token iat.
    ("token_epoch", "token_epoch DOUBLE PRECISION DEFAULT 0"),
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


# ── uniqueness that outlived its meaning ─────────────────────────────────────
# Several columns were declared globally UNIQUE when their table was first
# created, and were later corrected to "unique per org". ``create_all`` only
# creates missing *tables* — it never alters an index that already exists. So a
# database created before the correction goes on enforcing globally what is now
# scoped to a single workspace: the second company to name an agent
# "protocol-assistant", or to mention an entity another company already
# mentions, gets an integrity error and a failed request.
#
# A database created from today's models has no such index, which is why this
# was invisible in development and in every test, and only surfaced when two
# workspaces on the live deployment picked the same industry.
#
# Nothing here is hardcoded to the two columns that happened to drift first.
# The database is compared against today's models, so any column that drifts
# later is repaired the same way without anyone having to notice.


def stale_global_uniques() -> list[dict[str, str]]:
    """Every single-column UNIQUE the database still enforces that today's
    models do not. Read-only: safe to call from a health check."""
    from sqlalchemy import inspect

    insp = inspect(engine)
    present = set(insp.get_table_names())
    found: list[dict[str, str]] = []

    for table in Base.metadata.tables.values():
        if table.name not in present:
            continue

        def _drifted(columns: list[str]) -> str | None:
            """The column name, if the database is stricter than the model."""
            if len(columns) != 1:
                return None                      # composite (org_id, x) — the fix itself
            col = table.columns.get(columns[0])
            if col is None or col.unique or col.primary_key:
                return None                      # the model agrees, or it is the key
            return columns[0]

        # A plain UNIQUE INDEX...
        for index in insp.get_indexes(table.name):
            if not index.get("unique"):
                continue
            column = _drifted(list(index.get("column_names") or []))
            if column and index.get("name"):
                found.append({"table": table.name, "column": column,
                              "name": index["name"], "kind": "index"})

        # ...and a UNIQUE CONSTRAINT, which PostgreSQL reports separately and
        # which needs ALTER TABLE rather than DROP INDEX to remove.
        try:
            constraints = insp.get_unique_constraints(table.name)
        except NotImplementedError:              # pragma: no cover — older dialects
            constraints = []
        for uc in constraints:
            column = _drifted(list(uc.get("column_names") or []))
            if column and uc.get("name"):
                found.append({"table": table.name, "column": column,
                              "name": uc["name"], "kind": "constraint"})

    return found


def missing_cascades() -> list[dict[str, str]]:
    """Foreign keys the models declare ``ON DELETE CASCADE`` that the database
    still enforces without it. Read-only: safe to call from a health check.

    Same blind spot as the unique indexes above — ``create_all`` will not alter
    a constraint on a table that already exists — but this one fails in a way
    that looks like nothing at all. Deleting a parent row raises only when a
    child happens to exist at that instant, so it depends on timing: fine in
    every test, fine by hand, and broken for a visitor whose click lands while
    a background job is still writing.
    """
    from sqlalchemy import inspect

    insp = inspect(engine)
    present = set(insp.get_table_names())
    gaps: list[dict[str, str]] = []

    for table in Base.metadata.tables.values():
        if table.name not in present:
            continue

        wanted = {
            col.name: (fk.column.table.name, fk.column.name)
            for col in table.columns
            for fk in col.foreign_keys
            if (fk.ondelete or "").upper() == "CASCADE"
        }
        if not wanted:
            continue

        for existing in insp.get_foreign_keys(table.name):
            columns = existing.get("constrained_columns") or []
            if len(columns) != 1 or columns[0] not in wanted:
                continue
            if ((existing.get("options") or {}).get("ondelete") or "").upper() == "CASCADE":
                continue
            parent, parent_column = wanted[columns[0]]
            gaps.append({"table": table.name, "column": columns[0],
                         "name": existing.get("name") or "",
                         "parent": parent, "parent_column": parent_column})

    return gaps


def add_missing_cascades() -> list[str]:
    """Repair what :func:`missing_cascades` finds. Returns what changed.

    Skipped on SQLite, which cannot alter a constraint — and does not need to,
    because a SQLite database here is always built fresh from today's models.
    """
    import logging

    from sqlalchemy import text

    log = logging.getLogger("eaios")
    if _is_sqlite:
        return []

    repaired: list[str] = []
    for gap in missing_cascades():
        table, column, name = gap["table"], gap["column"], gap["name"]
        if not name:
            continue
        try:
            with engine.begin() as conn:      # its own transaction, as above
                conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"'))
                conn.execute(text(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
                    f'FOREIGN KEY ("{column}") '
                    f'REFERENCES "{gap["parent"]}" ("{gap["parent_column"]}") ON DELETE CASCADE'))
            repaired.append(f"{table}.{column}")
            log.info("%s.%s now cascades on delete", table, column)
        except Exception as exc:   # noqa: BLE001 — never block startup
            log.warning("could not add ON DELETE CASCADE to %s.%s: %s", table, column, exc)

    return repaired


def create_missing_indexes() -> list[str]:
    """Create any index the models declare that the live table is missing.

    ``create_all`` builds indexes only for tables it creates; it never adds one
    to a table that already exists. So a column that gains ``index=True`` after
    its table shipped stays unindexed in production — full scans on every lookup
    and on the foreign-key checks a parent delete triggers. This closes that gap
    the same way the cascade repair does: compare models to the database, apply
    the difference, each in its own transaction, never fatal.
    """
    import logging

    from sqlalchemy import inspect, text

    log = logging.getLogger("eaios")
    insp = inspect(engine)
    present = set(insp.get_table_names())
    created: list[str] = []

    for table in Base.metadata.tables.values():
        if table.name not in present:
            continue
        have = {tuple(ix.get("column_names") or []) for ix in insp.get_indexes(table.name)}
        # a unique constraint already indexes its columns
        have |= {tuple(uc.get("column_names") or [])
                 for uc in insp.get_unique_constraints(table.name)}
        pk = tuple(insp.get_pk_constraint(table.name).get("constrained_columns") or [])
        for index in table.indexes:
            cols = tuple(c.name for c in index.columns)
            if not cols or cols in have or cols == pk:
                continue
            try:
                with engine.begin() as conn:
                    unique = "UNIQUE " if index.unique else ""
                    collist = ", ".join(f'"{c}"' for c in cols)
                    conn.execute(text(
                        f'CREATE {unique}INDEX IF NOT EXISTS "{index.name}" '
                        f'ON "{table.name}" ({collist})'))
                created.append(f"{table.name}({', '.join(cols)})")
                log.info("created missing index %s on %s", index.name, table.name)
            except Exception as exc:  # noqa: BLE001 — an index is an optimisation, never fatal
                log.warning("could not create index %s on %s: %s", index.name, table.name, exc)

    return created


def harden_column_types_and_checks() -> list[str]:
    """Bring an existing database up to the models' constraints and types.

    Two things ``create_all`` won't retrofit onto a live table:

      * the ``ck_users_role`` CHECK — so the database, not only the API, refuses
        an out-of-set role. Adding it validates existing rows; every real role
        is already in the set, so this is safe.
      * ``expires_at`` / ``verify_expires_at`` as ``timestamptz`` — the values
        were written as UTC, so we convert interpreting them ``AT TIME ZONE
        'UTC'``, and the app stops depending on each reader re-attaching UTC.

    Postgres-only (SQLite builds fresh from the models), idempotent, never fatal.
    """
    import logging

    from sqlalchemy import inspect, text

    if _is_sqlite:
        return []

    log = logging.getLogger("eaios")
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    done: list[str] = []

    # ── role CHECK ──────────────────────────────────────────────────────────
    if "users" in existing:
        have = {c.get("name") for c in insp.get_check_constraints("users")}
        if "ck_users_role" not in have:
            try:
                with engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE users ADD CONSTRAINT ck_users_role "
                        "CHECK (role IN ('admin', 'hr', 'manager', 'employee'))"))
                done.append("ck_users_role")
                log.info("added CHECK constraint ck_users_role")
            except Exception as exc:  # noqa: BLE001
                log.warning("could not add ck_users_role: %s", exc)

    # ── tz-aware expiry columns ─────────────────────────────────────────────
    for table, column in (("organizations", "expires_at"), ("users", "verify_expires_at")):
        if table not in existing:
            continue
        col = next((c for c in insp.get_columns(table) if c["name"] == column), None)
        if col is None:
            continue
        # only convert if it isn't already timezone-aware
        if getattr(col["type"], "timezone", False):
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE {table} ALTER COLUMN {column} TYPE TIMESTAMPTZ '
                    f"USING {column} AT TIME ZONE 'UTC'"))
            done.append(f"{table}.{column}=timestamptz")
            log.info("converted %s.%s to timestamptz", table, column)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not convert %s.%s to timestamptz: %s", table, column, exc)

    return done


def relax_stale_global_uniques() -> list[str]:
    """Repair what :func:`stale_global_uniques` finds. Returns what changed.

    Each repair gets its **own** transaction. On PostgreSQL a single failed
    statement poisons the entire transaction — every statement after it fails
    with "current transaction is aborted", and the commit silently becomes a
    rollback. Sharing one transaction would therefore mean a single awkward
    index quietly undoing every repair that had already succeeded, which looks
    exactly like the migration never running at all.
    """
    import logging

    from sqlalchemy import text

    log = logging.getLogger("eaios")
    repaired: list[str] = []

    for item in stale_global_uniques():
        table, column, name, kind = (item["table"], item["column"],
                                     item["name"], item["kind"])
        try:
            with engine.begin() as conn:
                if kind == "constraint":
                    conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"'))
                else:
                    conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                # The column is still looked up constantly — it loses the
                # uniqueness, not the index.
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS "ix_{table}_{column}" ON "{table}" ("{column}")'))
            repaired.append(f"{table}.{column}")
            log.info("relaxed stale global unique %s on %s.%s — now unique per workspace",
                     name, table, column)
        except Exception as exc:      # noqa: BLE001 — one stubborn index must not stop the rest
            log.warning("could not relax unique %s on %s.%s: %s", name, table, column, exc)

    return repaired


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
