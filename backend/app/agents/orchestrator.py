"""Multi-agent orchestrator — graph runtime with dynamic semantic routing.

The request flows through a compiled StateGraph (LangGraph semantics,
see ``app.agents.graph``):

                       ┌─▶ agent A ─┐
    START → router ────┼─▶ agent B ─┼──▶ merge → END      (LLM routing: fan-out,
                       └─▶ agent C ─┘                       branches run in PARALLEL)

    START → router → dispatch ─▶ agent ─▶ dispatch ─▶ … ─▶ merge → END
                                                            (regex fallback: sequential,
                                                             output chains step to step)

Routing tiers (ROUTER_MODE = auto | llm | regex):
1. **LLM semantic router** — a single fast LLM call classifies the query
   against the agent catalog and returns strict JSON:
   ``{"tasks": [{"agent": "document", "task": "…"}]}``. Each task must be
   independent and self-contained; the graph fans them out concurrently
   (each branch gets its own DB session — SQLAlchemy sessions are not
   thread-safe) and converges at ``merge``.
2. **Regex intent table** — transparent, deterministic, zero-cost. Used in
   ``auto`` mode when the LLM provider is the mock (tests/demo), whenever
   the router's JSON can't be validated, or when forced via config.
3. **Legacy sequential path** — if the graph itself ever fails, the REST
   contract is still honored.
"""
import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents.graph import END, START, CompiledGraph, StateGraph, list_concat
from app.agents.planning_agent import PlanningAgent
from app.agents.registry import AGENT_MAP
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.events import hub
from app.core.tracing import span
from app.models import User
from app.schemas import Citation

log = logging.getLogger("eaios.orchestrator")

INTENTS: list[tuple[str, re.Pattern]] = [
    ("memory",    re.compile(r"^(remember|note that|save this)|what do you (know|remember) about me", re.I)),
    ("sql",       re.compile(r"\b(sql|database|table|query|rows?|how many (users|documents|messages|conversations|runs))\b", re.I)),
    ("research",  re.compile(r"\b(search (the )?(web|internet)|latest news|news about|look up online|current price)\b", re.I)),
    ("email",     re.compile(r"\b(email|e-mail|draft (a )?(mail|reply)|reply to)\b", re.I)),
    ("report",    re.compile(r"\b(report|executive summary|briefing)\b", re.I)),
    ("analytics", re.compile(r"\b(analytics|usage|insight|kpi|dashboard|adoption|trend)\b", re.I)),
    ("coding",    re.compile(r"\b(code|coding|function|script|debug|refactor|regex|python|javascript|typescript|api endpoint|unit test|algorithm)\b", re.I)),
]


def route(text: str) -> str:
    for agent_id, pattern in INTENTS:
        if pattern.search(text):
            return agent_id
    return "document"  # default: RAG over the knowledge base


# ── LLM semantic router ──────────────────────────────────────────────────
ROUTER_SYSTEM = (
    "You are the routing brain of EAIOS, an enterprise AI platform. "
    "Decide which specialist agents must run to fully answer the user's request.\n\n"
    "Available agents:\n"
    "- document: answers questions from the indexed company knowledge base (policies, financials, manuals) with citations\n"
    "- sql: converts natural language into safe read-only SQL over the platform database and returns results\n"
    "- research: live web search for news, facts, prices, anything outside company documents\n"
    "- email: drafts professional emails and replies\n"
    "- report: writes structured reports and executive summaries\n"
    "- analytics: usage KPIs, adoption metrics, platform insights\n"
    "- memory: stores or recalls long-term facts and preferences about the user\n"
    "- coding: explains, generates, reviews or debugs code\n\n"
    "Rules:\n"
    "1. Return ONLY JSON, no prose: {\"tasks\": [{\"agent\": \"<id>\", \"task\": \"<self-contained instruction>\"}]}\n"
    "2. Use the fewest agents that fully cover the request (usually 1, max 4).\n"
    "3. Tasks run IN PARALLEL, so each task text must stand alone — copy any needed context into it.\n\n"
    "Example — request: \"How many annual leave days do we get, and draft an email to HR asking to carry days over?\"\n"
    "{\"tasks\": [{\"agent\": \"document\", \"task\": \"How many annual leave days do employees get per year?\"}, "
    "{\"agent\": \"email\", \"task\": \"Draft a professional email to HR asking whether unused annual leave days can be carried over to next year.\"}]}"
)

MAX_ROUTED_TASKS = 4


def parse_router_json(raw: str) -> list[tuple[str, str]] | None:
    """Validate the router's JSON → [(agent_id, task)] or None if unusable."""
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(raw[start:end + 1])
        tasks = data.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            return None
        out: list[tuple[str, str]] = []
        seen: dict[str, int] = {}
        for item in tasks[:MAX_ROUTED_TASKS]:
            agent = str(item.get("agent", "")).strip().lower()
            task = str(item.get("task", "")).strip()
            if agent not in AGENT_MAP or agent == "planning" or not task:
                continue
            if agent in seen:  # one node per agent: merge duplicate tasks
                idx = seen[agent]
                out[idx] = (agent, f"{out[idx][1]} Also: {task}")
            else:
                seen[agent] = len(out)
                out.append((agent, task))
        return out or None
    except Exception:  # noqa: BLE001 — any malformed output → regex fallback
        return None


def semantic_route(text: str) -> list[tuple[str, str]] | None:
    """One fast LLM call → validated routing plan, or None → regex fallback."""
    mode = settings.ROUTER_MODE.lower()
    if mode == "regex":
        return None
    from app.llm.provider import get_llm

    llm = get_llm()
    if mode == "auto" and llm.name == "mock":
        return None  # deterministic demo/tests: keep the transparent regex path
    try:
        with span("semantic_router", kind="llm", model=getattr(llm, "model", llm.name)):
            raw = llm.complete(ROUTER_SYSTEM, f"Request: {text}\n\nJSON:")
        routed = parse_router_json(raw)
        if routed:
            log.info("semantic router → %s", [a for a, _ in routed])
        else:
            log.warning("semantic router output unusable — falling back to regex")
        return routed
    except Exception as exc:  # noqa: BLE001
        log.warning("semantic router failed (%s) — falling back to regex", exc)
        return None


@dataclass
class OrchestratorResult:
    answer: str
    agent: str
    plan: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: int = 70
    timeline: list[dict] = field(default_factory=list)

    @property
    def citations_json(self) -> str:
        return json.dumps([c.model_dump() for c in self.citations])


class Orchestrator:
    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user

    # ── graph construction ───────────────────────────────────────────────
    def build_graph(self) -> CompiledGraph:
        g = StateGraph(reducers={
            "answers": list_concat,
            "citations": list_concat,
            "confidences": list_concat,
            "agents_used": list_concat,
        })
        g.add_node("router", self._node_router)
        g.add_node("merge", self._node_merge)
        for agent_id in AGENT_MAP:
            if agent_id == "planning":
                continue
            g.add_node(agent_id, self._make_agent_node(agent_id))
            g.add_conditional_edges(agent_id, self._after_agent)
        g.add_edge(START, "router")
        g.add_conditional_edges("router", self._after_router)
        g.add_edge("merge", END)
        return g.compile()

    # ── nodes ────────────────────────────────────────────────────────────
    def _node_router(self, state: dict) -> dict:
        text = state["text"]
        if state.get("force_agent"):
            return {"route_mode": "forced", "queue": [(state["force_agent"], text)],
                    "planned": False, "total_steps": 1}

        routed = semantic_route(text)
        if routed:
            return {
                "route_mode": "llm",
                "task_map": dict(routed),
                "planned": len(routed) > 1,
                "total_steps": len(routed),
            }

        with span("planner", kind="agent", input=text[:120]):
            subtasks = PlanningAgent(self.db, self.user).decompose(text)
        queue = [(route(sub), sub) for sub in subtasks]
        return {"route_mode": "regex", "queue": queue,
                "planned": len(queue) > 1, "total_steps": len(queue)}

    def _after_router(self, state: dict) -> "str | list[str]":
        task_map = state.get("task_map")
        if task_map:
            return list(task_map.keys())  # fan-out: parallel branches
        queue = state.get("queue") or []
        return queue[0][0] if queue else "merge"

    def _after_agent(self, state: dict) -> str:
        if state.get("task_map"):
            return "merge"  # parallel branches converge
        queue = state.get("queue") or []
        return queue[0][0] if queue else "merge"

    def _make_agent_node(self, agent_id: str):
        def node(state: dict) -> dict:
            parallel = bool(state.get("task_map"))
            if parallel:
                subtask = state["task_map"][agent_id]
                task = subtask
            else:
                queue = list(state["queue"])
                _aid, subtask = queue.pop(0)
                previous = state.get("previous_output", "")
                task = subtask if not previous else \
                    f"{subtask}\n\n(Previous step output for reference: {previous[:500]})"

            hub.publish("agent.step", agent=agent_id, status="start",
                        task=subtask[:140], user=self.user.full_name)

            if parallel:
                # own session per thread — SQLAlchemy sessions are not thread-safe
                with SessionLocal() as db:
                    user = db.get(User, self.user.id) or self.user
                    agent = AGENT_MAP[agent_id](db, user)
                    with span(agent.name, kind="agent", task=subtask[:120], parallel=True) as s:
                        result = agent.run(task)
                        if s is not None:
                            s["attrs"]["confidence"] = result.confidence
            else:
                agent = AGENT_MAP[agent_id](self.db, self.user)
                with span(agent.name, kind="agent", task=subtask[:120]) as s:
                    result = agent.run(task)
                    if s is not None:
                        s["attrs"]["confidence"] = result.confidence

            hub.publish("agent.step", agent=agent_id, status="done",
                        task=subtask[:140], user=self.user.full_name,
                        confidence=result.confidence)

            name = AGENT_MAP[agent_id].name
            label = f"**{name}** — {result.answer}" if state.get("total_steps", 1) > 1 else result.answer
            update: dict = {
                "answers": [label],
                "citations": list(result.citations),
                "confidences": [result.confidence],
                "agents_used": [agent_id],
            }
            if not parallel:
                update["queue"] = queue
                update["previous_output"] = result.answer
            return update

        return node

    def _node_merge(self, state: dict) -> dict:
        answers = state.get("answers") or ["I could not produce an answer for that request."]
        agents_used = state.get("agents_used", [])
        confidences = state.get("confidences", [])
        return {
            "final_answer": "\n\n".join(answers),
            "final_agent": agents_used[0] if len(agents_used) == 1 else "planning",
            "final_confidence": min(confidences) if confidences else 50,
        }

    # ── public API (unchanged contract) ──────────────────────────────────
    def handle(self, text: str, force_agent: str | None = None) -> OrchestratorResult:
        if force_agent and force_agent not in AGENT_MAP:
            force_agent = None
        try:
            return self._handle_graph(text, force_agent)
        except Exception:  # noqa: BLE001 — graph must never take down chat
            log.exception("graph execution failed — using legacy sequential path")
            return self._handle_legacy(text, force_agent)

    def _handle_graph(self, text: str, force_agent: str | None) -> OrchestratorResult:
        graph = self.build_graph()
        state = graph.invoke({"text": text, "force_agent": force_agent})
        mode = state.get("route_mode", "regex")
        agents_used = state.get("agents_used", [])
        if mode == "llm":
            plan = ["router", *agents_used]
        else:
            plan = (["planning"] if state.get("planned") else []) + agents_used
        return OrchestratorResult(
            answer=state["final_answer"],
            agent=state["final_agent"],
            plan=plan,
            citations=state.get("citations", [])[:10],
            confidence=state["final_confidence"],
            timeline=state.get("timeline", []),
        )

    # Legacy sequential path — retained as a safety net.
    def _handle_legacy(self, text: str, force_agent: str | None = None) -> OrchestratorResult:
        if force_agent and force_agent in AGENT_MAP:
            steps = [(force_agent, text)]
            planned = False
        else:
            subtasks = PlanningAgent(self.db, self.user).decompose(text)
            steps = [(route(sub), sub) for sub in subtasks]
            planned = len(steps) > 1

        answers: list[str] = []
        citations: list[Citation] = []
        confidences: list[int] = []
        plan = (["planning"] if planned else []) + [agent_id for agent_id, _ in steps]

        previous_output = ""
        for agent_id, subtask in steps:
            agent = AGENT_MAP[agent_id](self.db, self.user)
            task = subtask if not previous_output else f"{subtask}\n\n(Previous step output for reference: {previous_output[:500]})"
            result = agent.run(task)
            answers.append(result.answer if len(steps) == 1 else f"**{agent.name}** — {result.answer}")
            citations.extend(result.citations)
            confidences.append(result.confidence)
            previous_output = result.answer

        return OrchestratorResult(
            answer="\n\n".join(answers),
            agent=steps[-1][0] if len(steps) == 1 else "planning",
            plan=plan,
            citations=citations[:10],
            confidence=min(confidences) if confidences else 50,
        )


def orchestrator_graph_spec() -> dict:
    """Static graph structure for the UI (agents fleet map)."""
    nodes = ["router", *[a for a in AGENT_MAP if a != "planning"], "merge"]
    return {
        "entry": "router",
        "nodes": nodes,
        "edges": [{"from": "router", "to": "fan-out"}],
        "conditional": ["router", *[a for a in AGENT_MAP if a != "planning"]],
    }
