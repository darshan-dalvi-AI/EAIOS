"""The SQL agent's tenant guard, attacked the way it actually broke.

The guard rewrites every tenant-table reference in raw SQL into an
org-scoped subquery — it exists precisely because the ORM auto-filter cannot
see ``text()`` SQL. It used to find those references with the pattern
``\\b(from|join)\\s+"?name"?``. Two lexical forms slipped past it and were
therefore executed with NO org filter, returning every workspace's rows:

    SELECT * FROM public.tasks     -- schema-qualified: regex saw "public"
    SELECT * FROM"tasks"           -- no space before the quote: regex saw nothing

Both are things the generating LLM can emit — on request, or spontaneously,
since so much training SQL is schema-qualified. These tests pin the fix:
qualified names are refused, no-space references are scoped, and two tenants
never see each other's rows.
"""
import secrets

import pytest

from app.agents.sql_agent import SQLAgent, _GuardReject
from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models import Organization, Task, User
from app.services import tenancy


def _agent_for(org_id: str) -> tuple[SQLAgent, object]:
    """A SQLAgent whose session is scoped to one workspace, as a request is."""
    db = SessionLocal()
    db.info["org_id"] = org_id
    user = db.query(User).filter(User.org_id == org_id).first()
    return SQLAgent(db, user), db


@pytest.fixture
def two_tenants():
    """Two workspaces, each with one uniquely-named task."""
    init_db()  # the schema is normally created by the app lifespan
    db = SessionLocal()
    made = {}
    try:
        for slug, secret in (("iso-alpha", "ALPHA-ISOLATION-SECRET"),
                             ("iso-beta", "BETA-ISOLATION-SECRET")):
            org = tenancy.create_org(db, slug)
            db.info["org_id"] = org.id
            u = User(email=f"admin-{secrets.token_hex(4)}@{slug}.example.com",
                     full_name="Admin", hashed_password=hash_password("x"),
                     role="admin", org_id=org.id)
            db.add(u)
            db.flush()
            db.add(Task(title=secret, status="todo", org_id=org.id, owner_id=u.id))
            db.commit()
            made[slug] = org.id
    finally:
        db.close()
    return made


# ── the reference forms that leaked ─────────────────────────────────────────

QUALIFIED = [
    "SELECT * FROM public.tasks",
    'SELECT * FROM public."tasks"',
    'SELECT * FROM "public"."tasks"',
    "SELECT * FROM\tpublic.tasks",
    "SELECT email FROM public.users",
]


@pytest.mark.parametrize("sql", QUALIFIED)
def test_schema_qualified_names_are_refused(two_tenants, sql):
    agent, db = _agent_for(two_tenants["iso-alpha"])
    try:
        with pytest.raises(_GuardReject):
            agent._tenant_scope(sql)
    finally:
        db.close()


def test_no_space_before_quote_is_still_scoped(two_tenants):
    """``FROM"tasks"`` was invisible to the old regex and executed unscoped."""
    agent, db = _agent_for(two_tenants["iso-alpha"])
    try:
        out, params = agent._tenant_scope('SELECT title FROM"tasks"')
        assert "org_id = :org" in out, out
        assert params.get("org") == two_tenants["iso-alpha"]
    finally:
        db.close()


def test_a_bare_tenant_table_is_scoped_not_rejected(two_tenants):
    agent, db = _agent_for(two_tenants["iso-alpha"])
    try:
        out, params = agent._tenant_scope("SELECT * FROM tasks")
        assert "org_id = :org" in out
        assert params["org"] == two_tenants["iso-alpha"]
    finally:
        db.close()


# ── the data, end to end: A must never see B ────────────────────────────────

@pytest.mark.parametrize("payload", [
    "SELECT * FROM public.tasks",
    'SELECT title FROM public."tasks"',
    'SELECT title FROM"tasks"',
    "SELECT * FROM tasks",
])
def test_one_tenant_never_sees_another_through_the_sql_agent(two_tenants, payload):
    """Drive the full answer() pipeline as alpha; beta's secret must not appear."""
    agent, db = _agent_for(two_tenants["iso-alpha"])
    try:
        agent._generate = lambda _q, p=payload: p   # stand in for the LLM
        out = agent.answer("(engineered question)")
        flat = str(out.rows)
        assert "BETA-ISOLATION-SECRET" not in flat, (
            f"cross-tenant leak via {payload!r}: {flat[:200]}")
    finally:
        db.close()


def test_rls_backstop_is_a_safe_noop_on_sqlite(two_tenants):
    """The RLS backstop is Postgres-only. On the SQLite suite it must disable
    itself cleanly so the SQL agent falls back to the regex guard — which is
    exactly what every other test in this file exercises. (The real RLS
    enforcement is verified against PostgreSQL, where a role can be switched.)
    """
    from app.core import database as db_module

    assert db_module.setup_sql_agent_rls() is False, "RLS setup must no-op on SQLite"
    assert db_module.rls_enabled() is False, "the agent must use the fallback path on SQLite"

    # And a query still runs and stays scoped through the fallback.
    agent, db = _agent_for(two_tenants["iso-alpha"])
    try:
        out = agent._run_query(
            "SELECT * FROM (SELECT * FROM tasks WHERE org_id = :org) AS tasks",
            {"org": two_tenants["iso-alpha"]})
        columns, rows = out
        assert not any("BETA-ISOLATION-SECRET" in str(cell) for row in rows for cell in row)
    finally:
        db.close()


def test_legitimate_queries_still_work(two_tenants):
    """The fix must not turn ordinary formatting into a rejection."""
    agent, db = _agent_for(two_tenants["iso-alpha"])
    try:
        for sql in ("SELECT * FROM tasks",
                    "SELECT *\n  FROM tasks\n  WHERE status = 'todo'",
                    "SELECT COUNT(*) FROM tasks WHERE status='todo'"):
            out, params = agent._tenant_scope(sql)
            assert "org_id = :org" in out, f"{sql!r} was not scoped: {out}"
    finally:
        db.close()
