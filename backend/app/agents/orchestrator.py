"""Multi-agent orchestrator — graph runtime edition.

The request flows through a compiled StateGraph (LangGraph semantics,
see ``app.agents.graph``):

    START → planner ──▶ dispatch ──▶ <agent node> ─┐
                            ▲                      │
                            └──────────────────────┘   (loop until queue empty)
                        dispatch ──▶ merge → END

- ``planner`` decomposes compound requests into subtasks (PlanningAgent).
- ``dispatch`` is a conditional edge: routes the next subtask to one of the
  8 specialist agents via the transparent regex intent table (explainable in
  a viva; swap for an LLM router without touching the API layer).
- Every node emits ``agent.step`` events to the realtime hub and records a
  span in the active trace.
- If the graph fails for any reason, a sequential legacy path produces the
  same result shape — the REST contract never breaks.
"""
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents.graph import END, START, CompiledGraph, StateGraph
from app.agents.planning_agent import PlanningAgent
from app.agents.registry import AGENT_MAP
from app.core.events import hub
from app.core.tracing import span
from app.models import User
from app.schemas import Citation

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
        import json

        return json.dumps([c.model_dump() for c in self.citations])


class Orchestrator:
    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user

    # ── graph construction ───────────────────────────────────────────────
    def build_graph(self) -> CompiledGraph:
        g = StateGraph()
        g.add_node("planner", self._node_planner)
        g.add_node("merge", self._node_merge)
        for agent_id in AGENT_MAP:
            if agent_id == "planning":
                continue
            g.add_node(agent_id, self._make_agent_node(agent_id))
            g.add_conditional_edges(agent_id, self._dispatch)
        g.add_edge(START, "planner")
        g.add_conditional_edges("planner", self._dispatch)
        g.add_edge("merge", END)
        return g.compile()

    def _node_planner(self, state: dict) -> dict:
        text = state["text"]
        if state.get("force_agent"):
            return {"queue": [(state["force_agent"], text)], "planned": False}
        with span("planner", kind="agent", input=text[:120]):
            subtasks = PlanningAgent(self.db, self.user).decompose(text)
        queue = [(route(sub), sub) for sub in subtasks]
        return {"queue": queue, "planned": len(queue) > 1, "total_steps": len(queue)}

    def _dispatch(self, state: dict) -> str:
        queue = state.get("queue") or []
        return queue[0][0] if queue else "merge"

    def _make_agent_node(self, agent_id: str):
        def node(state: dict) -> dict:
            queue = list(state["queue"])
            _aid, subtask = queue.pop(0)
            agent = AGENT_MAP[agent_id](self.db, self.user)
            previous = state.get("previous_output", "")
            task = subtask if not previous else f"{subtask}\n\n(Previous step output for reference: {previous[:500]})"
            hub.publish("agent.step", agent=agent_id, status="start",
                        task=subtask[:140], user=self.user.full_name)
            with span(agent.name, kind="agent", task=subtask[:120]) as s:
                result = agent.run(task)
                if s is not None:
                    s["attrs"]["confidence"] = result.confidence
            hub.publish("agent.step", agent=agent_id, status="done",
                        task=subtask[:140], user=self.user.full_name,
                        confidence=result.confidence)
            label = f"**{agent.name}** — {result.answer}" if state.get("total_steps", 1) > 1 else result.answer
            return {
                "queue": queue,
                "answers": [*state.get("answers", []), label],
                "citations": [*state.get("citations", []), *result.citations],
                "confidences": [*state.get("confidences", []), result.confidence],
                "agents_used": [*state.get("agents_used", []), agent_id],
                "previous_output": result.answer,
            }

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
            return self._handle_legacy(text, force_agent)

    def _handle_graph(self, text: str, force_agent: str | None) -> OrchestratorResult:
        graph = self.build_graph()
        state = graph.invoke({"text": text, "force_agent": force_agent})
        plan = (["planning"] if state.get("planned") else []) + state.get("agents_used", [])
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
    nodes = ["planner", *[a for a in AGENT_MAP if a != "planning"], "merge"]
    return {
        "entry": "planner",
        "nodes": nodes,
        "edges": [{"from": "planner", "to": "dispatch"}],
        "conditional": ["planner", *[a for a in AGENT_MAP if a != "planning"]],
    }
