"""SQL Agent — natural language → validated, read-only SQL.

Defense in depth: single-statement check, SELECT-only allowlist, keyword
blocklist, forced LIMIT, and execution inside the request's own session."""
import logging
import re

from sqlalchemy import text

from app.core.config import settings
from app.agents.base import AgentResult, BaseAgent
from app.core.database import Base
from app.llm.provider import safe_complete
from app.schemas import SQLOut

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|pragma|grant|revoke|replace|vacuum)\b", re.I
)
log = logging.getLogger("eaios.sql")

MAX_ROWS = 50
MAX_SQL_RETRIES = 2  # reflection loop: error → LLM rewrite → retry

# ── multi-tenant isolation for raw SQL ───────────────────────────
# The ORM auto-filter (core.database) only scopes ORM select() statements;
# it CANNOT see raw text() SQL. So the SQL agent gets its own guard: every
# tenant table referenced is transparently rewritten into an org-scoped
# subquery, and anything the guard can't prove is isolated is rejected
# (fail-closed). Result: a user in one workspace can never read another's rows.
TENANT_TABLES = {
    "users", "documents", "chunks", "conversations", "messages", "agent_runs",
    "memory_entries", "audit_logs", "entities", "entity_edges", "entity_mentions",
    "workflows", "workflow_runs", "data_tables", "graph_checkpoints",
    "custom_agents", "connectors", "saved_charts", "tasks", "usage_events",
}
SENSITIVE_DENY = {"organizations"}  # the tenant registry itself — never exposed
# Tokens that may legally follow a table name (i.e. NOT an alias). Anything
# else after a table (an alias, or a comma-join) means we can't safely inject
# the org filter, so we refuse rather than risk a leak.
_SAFE_FOLLOWERS = {
    "", "where", "group", "order", "limit", "having", "union", "join",
    "inner", "left", "right", "full", "cross", "on", "offset",
}
# Matches FROM/JOIN and the table reference that follows. Deliberately broader
# than "keyword + space + name":
#   * ``\s*`` (not ``\s+``) so ``FROM"users"`` with no space is still seen —
#     otherwise the reference is invisible to the guard and passes UNSCOPED.
#   * group 3 captures a schema qualifier (``public.users``,
#     ``pg_catalog.pg_tables``). A regex cannot scope a qualified name, so the
#     guard rejects any it finds rather than letting it through unscoped.
# Both forms bypassed the previous ``\s+"?name"?`` pattern and leaked every
# other workspace's rows; see tests/test_sql_tenant_isolation.py.
_TABLE_REF = re.compile(
    r'\b(from|join)\b\s*("?[a-zA-Z_]\w*"?)(\s*\.\s*"?[a-zA-Z_]\w*"?)?', re.I)


class _GuardReject(Exception):
    """Raised when a query can't be guaranteed to stay inside one workspace."""

SYSTEM = (
    "You are the SQL Agent. Generate a single read-only SQL SELECT statement for the schema below. "
    "Return ONLY the SQL, no prose, no code fences."
)


class SQLAgent(BaseAgent):
    id = "sql"
    name = "SQL Agent"
    description = "Converts natural language into safe, read-only SQL and executes it against the platform database."
    capabilities = ["NL → SQL generation", "Read-only guardrails", "Schema explanation", "Result tables"]

    # ── public API (used by /agents/sql route) ───────────────────
    def answer(self, question: str) -> SQLOut:
        """Generate → validate → execute, with a self-correcting reflection
        loop: execution errors are fed back to the LLM (traceback included)
        so it can rewrite the query — up to MAX_SQL_RETRIES times — before
        the user ever sees a failure."""
        sql = self._generate(question)
        last_error = ""
        for attempt in range(1 + MAX_SQL_RETRIES):
            problem = self._validate(sql)
            if problem:
                return SQLOut(sql=sql, explanation="Query rejected by safety guardrails.", warning=problem)

            try:
                scoped, params = self._tenant_scope(sql)
            except _GuardReject as rej:
                return SQLOut(sql=sql, explanation="Query rejected by workspace isolation.", warning=str(rej))

            try:
                result = self.db.execute(text(scoped), params)
                columns = list(result.keys())
                rows = [[_cell(v) for v in row] for row in result.fetchmany(MAX_ROWS)]
                corrected = f" Self-corrected after {attempt} failed attempt(s)." if attempt else ""
                return SQLOut(
                    sql=sql,
                    explanation=f"Returned {len(rows)} row(s) across {len(columns)} column(s). "
                                f"Read-only guardrails enforced (SELECT-only, LIMIT {MAX_ROWS}).{corrected}",
                    columns=columns,
                    rows=rows,
                )
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()  # a failed execute leaves the session in a dead transaction
                last_error = str(exc)[:300]
                fixed = self._reflect(question, sql, last_error)
                if not fixed or fixed == sql:
                    break
                sql = fixed

        # The raw database error can expose schema details, so the caller sees
        # a generic note while the full text stays in the server log.
        from app.core import errors
        safe = errors.redact(last_error)[:180] if settings.SQL_SHOW_DB_ERRORS else \
            "The query could not be executed. Try rephrasing the question."
        log.warning("sql agent failed after retries: %s", errors.redact(last_error)[:400])
        return SQLOut(sql=sql, explanation="Execution failed (after self-correction attempts).", warning=safe)

    def _reflect(self, question: str, failed_sql: str, error: str) -> str | None:
        """Reflection loop: ask the LLM to repair its own query. No-op on mock."""
        from app.llm.provider import get_llm

        if get_llm().name == "mock":
            return None
        try:
            raw = safe_complete(
                "You are the SQL Agent's self-correction step. The SQL you wrote failed. "
                "Fix it. Return ONLY the corrected single read-only SELECT statement — no prose, no fences.",
                f"SCHEMA:\n{schema_description(self.db)}\n\nQUESTION: {question}\n\n"
                f"FAILED SQL:\n{failed_sql}\n\nDATABASE ERROR:\n{error}\n\nCorrected SQL:",
            )
            fixed = raw.strip().strip("`").removeprefix("sql").strip()
            return fixed if fixed.lower().startswith("select") else None
        except Exception:  # noqa: BLE001
            return None

    def _run(self, task: str) -> AgentResult:
        out = self.answer(task)
        if out.warning:
            return AgentResult(answer=f"SQL blocked or failed: {out.warning}\n\n```sql\n{out.sql}\n```", confidence=30)
        preview = "\n".join(" | ".join(str(v) for v in row) for row in out.rows[:8])
        answer = (
            f"I generated and executed this query:\n\n```sql\n{out.sql}\n```\n\n"
            f"{out.explanation}\n\n{' | '.join(out.columns)}\n{preview}"
        )
        return AgentResult(answer=answer, confidence=85)

    # ── generation ───────────────────────────────────────────────
    def _generate(self, question: str) -> str:
        q = question.lower()
        heuristic = self._data_table_heuristic(q) or self._heuristic(q)
        if heuristic:
            return heuristic
        sql = safe_complete(SYSTEM, f"SCHEMA:\n{schema_description(self.db)}\n\nQUESTION: {question}")
        sql = sql.strip().strip("`").removeprefix("sql").strip()
        # Mock provider returns prose, not SQL — fall back to a sensible default.
        if not sql.lower().startswith("select"):
            return "SELECT doc_type, COUNT(*) AS total FROM documents GROUP BY doc_type"
        return sql

    def _data_table_heuristic(self, q: str) -> str | None:
        """Uploaded structured tables (advanced document parsing): if the
        question names a document/table that was materialized, query it
        directly — precise structured retrieval instead of text chunks."""
        from app.models import DataTable

        try:
            for dt in self.db.query(DataTable).order_by(DataTable.created_at.desc()).limit(50):
                names = {dt.table_name.lower(), dt.title.lower(), dt.doc_title.lower()}
                if any(n and n in q for n in names):
                    if "how many" in q or "count" in q:
                        return f'SELECT COUNT(*) AS total FROM "{dt.table_name}"'
                    return f'SELECT * FROM "{dt.table_name}" LIMIT 20'
        except Exception:  # noqa: BLE001 — heuristic only
            return None
        return None

    def _heuristic(self, q: str) -> str | None:
        """Template routes for the most common analytical asks."""
        table = next((t for t in ("users", "documents", "conversations", "messages", "agent_runs", "audit_logs") if t.rstrip("s") in q or t in q), None)
        if "how many" in q or "count" in q or "number of" in q:
            if table:
                return f"SELECT COUNT(*) AS total FROM {table}"
        if table == "documents" and ("type" in q or "by" in q):
            return "SELECT doc_type, COUNT(*) AS total FROM documents GROUP BY doc_type ORDER BY total DESC"
        if table == "users" and "role" in q:
            return "SELECT role, COUNT(*) AS total FROM users GROUP BY role"
        if table == "agent_runs":
            return "SELECT agent, COUNT(*) AS runs, AVG(duration_ms) AS avg_ms FROM agent_runs GROUP BY agent ORDER BY runs DESC"
        if ("recent" in q or "latest" in q or "last" in q) and table:
            return f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT 10"
        if table:
            return f"SELECT * FROM {table} LIMIT 20"
        return None

    # ── multi-tenant isolation ───────────────────────────────────
    def _tenant_scope(self, sql: str):
        """Rewrite raw SQL so it can only touch the caller's own workspace.

        Returns (sql, params). When no org context is active (system/single-
        tenant paths) the query is returned unchanged. Otherwise every tenant
        table is replaced by ``(SELECT * FROM t WHERE org_id = :org) AS t`` and
        anything that can't be safely scoped is rejected via ``_GuardReject``."""
        org_id = self.db.info.get("org_id")
        if not org_id:
            return sql, {}

        # dt_* tables the caller legitimately owns (this query is ORM-scoped,
        # so it already only returns THIS workspace's extracted tables).
        allowed_dt = set()
        try:
            from app.models import DataTable
            allowed_dt = {name for (name,) in self.db.query(DataTable.table_name).all()}
        except Exception:  # noqa: BLE001
            pass

        # Collect edits by position, then apply right-to-left so offsets stay
        # valid and injected text is never re-scanned (handles self-joins).
        edits = []
        for m in _TABLE_REF.finditer(sql):
            # A schema-qualified reference (public.users, pg_catalog.pg_tables)
            # cannot be scoped by rewriting the bare name, so refuse it. The app's
            # own queries never qualify — schema_description() lists bare names —
            # so this rejects only evasion, never legitimate use.
            if m.group(3):
                raise _GuardReject(
                    "Schema-qualified table names aren't allowed in workspace-scoped queries.")
            table = m.group(2).strip('"')
            tl = table.lower()
            if tl in SENSITIVE_DENY:
                raise _GuardReject(f"The '{table}' table isn't available in workspace-scoped queries.")
            if tl.startswith("dt_"):
                if table not in allowed_dt:
                    raise _GuardReject(f"Table '{table}' isn't in your workspace.")
                continue  # owned extracted table — safe as-is
            if tl not in TENANT_TABLES:
                continue  # non-tenant / unknown table — nothing to scope
            # Refuse if an alias or comma-join follows (can't inject safely).
            rest = sql[m.end():].lstrip()
            nxt = re.match(r'([),;]|\w+)', rest)
            follower = (nxt.group(1) if nxt else "").lower()
            if follower == ",":
                raise _GuardReject("Comma joins aren't supported for workspace-scoped queries — use explicit JOIN.")
            if follower not in _SAFE_FOLLOWERS and follower not in (")", ";"):
                raise _GuardReject("Query is too complex to guarantee workspace isolation — please simplify (avoid table aliases).")
            edits.append((m.start(), m.end(),
                          f"{m.group(1)} (SELECT * FROM {table} WHERE org_id = :org) AS {table}"))

        out = sql
        for start, end, repl in reversed(edits):
            out = out[:start] + repl + out[end:]
        return out, ({"org": org_id} if edits else {})

    # ── safety ───────────────────────────────────────────────────
    def _validate(self, sql: str) -> str:
        stripped = sql.strip().rstrip(";")
        if ";" in stripped:
            return "Multiple statements are not allowed."
        if not stripped.lower().startswith("select"):
            return "Only SELECT statements are permitted."
        if FORBIDDEN.search(stripped):
            return "Statement contains a forbidden keyword."
        if "--" in stripped or "/*" in stripped:
            return "Comments are not allowed."
        return ""


def schema_description(db=None) -> str:
    lines = []
    for table in Base.metadata.sorted_tables:
        cols = ", ".join(f"{c.name} {c.type}" for c in table.columns)
        lines.append(f"{table.name}({cols})")

    # structured tables extracted from uploaded documents (advanced parsing):
    # physical dt_* tables the LLM can target directly
    if db is not None:
        try:
            import json

            from app.models import DataTable

            for dt in db.query(DataTable).order_by(DataTable.created_at.desc()).limit(25):
                cols = ", ".join(f"{c['name']} {c['type']}" for c in json.loads(dt.columns or "[]"))
                lines.append(f"{dt.table_name}({cols})  -- '{dt.title}' extracted from document '{dt.doc_title}'")
        except Exception:  # noqa: BLE001 — schema listing must never fail
            pass
    return "\n".join(lines)


def _cell(v):
    return v if isinstance(v, (int, float, bool)) or v is None else str(v)
