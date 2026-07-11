"""EAIOS as an MCP server — expose the platform to any MCP client
(Claude Desktop, Cursor, custom agents) as a set of tools.

    pip install mcp
    python -m app.mcp_server          # stdio transport

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "eaios": {
          "command": "python",
          "args": ["-m", "app.mcp_server"],
          "cwd": "<repo>/backend"
        }
      }
    }

Tools operate directly on the local EAIOS database (same engine the web UI
uses), acting as the bootstrap admin user.
"""
import json

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The MCP SDK is not installed. Run:  pip install mcp"
    ) from exc

from app.core.database import SessionLocal, init_db
from app.models import User

mcp = FastMCP(
    "eaios",
    instructions="Enterprise AI Operating System — grounded answers over the "
                 "indexed company knowledge base, multi-agent execution, and "
                 "knowledge-graph queries.",
)


def _service_user(db) -> User:
    user = db.query(User).filter(User.role == "admin").first()
    if user is None:
        raise RuntimeError("No admin user — run `python -m app.seed` first")
    return user


@mcp.tool()
def search_knowledge(query: str, k: int = 6) -> str:
    """Hybrid search (BM25 + vectors) over the enterprise knowledge base.
    Returns the top passages with titles, sections, and relevance scores."""
    from app.rag.retrieval import hybrid_search

    with SessionLocal() as db:
        hits = hybrid_search(db, query, k=min(k, 12))
        if not hits:
            return "No matches in the knowledge base."
        return "\n\n".join(
            f"[{i + 1}] {r.title}" + (f" — {r.section}" if r.section else "") +
            f" (score {r.score:.2f})\n{r.text[:500]}"
            for i, r in enumerate(hits)
        )


@mcp.tool()
def ask_eaios(question: str, agent: str = "") -> str:
    """Ask the full multi-agent platform. The planner routes to the right
    specialist (document/sql/research/email/report/analytics/memory/coding);
    pass `agent` to force one. Returns the answer with citations."""
    from app.agents.orchestrator import Orchestrator

    with SessionLocal() as db:
        user = _service_user(db)
        result = Orchestrator(db, user).handle(question, force_agent=agent or None)
        cites = "".join(
            f"\n[{i + 1}] {c.title}" + (f" — {c.section}" if c.section else "")
            for i, c in enumerate(result.citations)
        )
        return (f"{result.answer}\n\n(agent: {result.agent} · plan: {' → '.join(result.plan) or result.agent} · "
                f"confidence: {result.confidence}%)" + (f"\n\nSources:{cites}" if cites else ""))


@mcp.tool()
def query_knowledge_graph(entity_a: str, entity_b: str) -> str:
    """How are two entities related? Returns the co-occurrence path,
    shared documents, and evidence passages from the knowledge graph."""
    from app.services import kgraph

    with SessionLocal() as db:
        rel = kgraph.relate(db, entity_a, entity_b)
        if rel is None:
            return "One or both entities were not found in the knowledge graph."
        # granular privacy flag — MCP clients count as agent access too
        from app.services import audit

        audit.flag_pii(db, None, "mcp.query_knowledge_graph", kgraph.sensitive_names(rel))
        return json.dumps(rel, indent=2, default=str)


@mcp.tool()
def list_agents() -> str:
    """List the EAIOS agent fleet with capabilities."""
    from app.agents import registry

    return "\n".join(f"- {a.id}: {a.name} — {a.description}" for a in registry.all_agents())


def main() -> None:
    init_db()
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
