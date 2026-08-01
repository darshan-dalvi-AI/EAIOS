"""Supabase/Postgres surface hardening.

Supabase publishes every ``public`` table through its REST API. K-OS never
uses that API, so the app shuts it: RLS on (deny-by-default, no policies) plus
the anon/authenticated grants revoked. These tests pin the emitted SQL and the
SQLite no-op, since the real behaviour can only be observed on Postgres.
"""
from unittest.mock import MagicMock

from app.core import database as db_mod
from app.rag import tables as tables_mod


def test_no_op_on_sqlite(monkeypatch):
    """Dev/test runs on SQLite must not attempt any Postgres-only DDL."""
    monkeypatch.setattr(db_mod, "_is_sqlite", True)
    called = MagicMock()
    monkeypatch.setattr(db_mod, "engine", called)
    db_mod.harden_public_schema()
    assert not called.begin.called


def _captured_sql(monkeypatch, tablenames):
    """Run harden_public_schema against a fake Postgres connection."""
    monkeypatch.setattr(db_mod, "_is_sqlite", False)
    executed: list[str] = []

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def first(self):
            return self._rows[0] if self._rows else None

        def __iter__(self):
            return iter(self._rows)

    class FakeConn:
        def execute(self, stmt, params=None):
            sql = str(stmt)
            executed.append(sql)
            if "pg_roles" in sql:
                return FakeResult([(1,)])                    # both API roles exist
            if "pg_tables" in sql:
                return FakeResult([(t,) for t in tablenames])
            return FakeResult([])

    class FakeBegin:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db_mod, "engine", type("E", (), {"begin": staticmethod(FakeBegin)})())
    db_mod.harden_public_schema()
    return executed


def test_enables_rls_and_revokes_api_grants_on_every_table(monkeypatch):
    sql = _captured_sql(monkeypatch, ["users", "documents", "dt_abc12345_1"])

    for table in ("users", "documents", "dt_abc12345_1"):
        assert f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'REVOKE ALL ON public."{table}" FROM anon' in sql
        assert f'REVOKE ALL ON public."{table}" FROM authenticated' in sql

    # No permissive policy is ever created — RLS with zero policies is the
    # deny-by-default we want for an API surface the app doesn't use.
    assert not any("CREATE POLICY" in s for s in sql)


def test_future_tables_inherit_no_api_grants(monkeypatch):
    sql = _captured_sql(monkeypatch, ["users"])
    for role in ("anon", "authenticated"):
        assert (f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role}") in sql


def test_hardening_never_blocks_startup(monkeypatch):
    """A permissions error must be logged, not raised — the app still boots."""
    monkeypatch.setattr(db_mod, "_is_sqlite", False)

    class Boom:
        @staticmethod
        def begin():
            raise RuntimeError("permission denied for schema public")

    monkeypatch.setattr(db_mod, "engine", Boom())
    db_mod.harden_public_schema()  # must not raise


def test_dt_tables_are_hardened_on_creation(monkeypatch):
    """Runtime-materialised dt_* tables are outside SQLAlchemy metadata, so
    they get hardened at creation time on the ingesting session."""
    monkeypatch.setattr(db_mod, "_is_sqlite", False)
    executed: list[str] = []

    class FakeSession:
        def begin_nested(self):
            class Ctx:
                def __enter__(self_i):
                    return None

                def __exit__(self_i, *a):
                    return False
            return Ctx()

        def execute(self, stmt):
            executed.append(str(stmt))

    tables_mod._harden(FakeSession(), "dt_deadbeef_1")
    assert 'ALTER TABLE public."dt_deadbeef_1" ENABLE ROW LEVEL SECURITY' in executed
    assert any("REVOKE ALL" in s and "anon" in s for s in executed)


def test_dt_hardening_is_skipped_on_sqlite(monkeypatch):
    monkeypatch.setattr(db_mod, "_is_sqlite", True)
    session = MagicMock()
    tables_mod._harden(session, "dt_deadbeef_1")
    assert not session.execute.called
