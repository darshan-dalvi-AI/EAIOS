"""Graph-based orchestration runtime — LangGraph's StateGraph model,
implemented dependency-free so the platform always boots.

API surface mirrors ``langgraph.graph.StateGraph`` (add_node / add_edge /
add_conditional_edges / set_entry_point / compile → invoke), so swapping in
the real library is a one-line import change. State is a plain dict; each
node returns a partial dict merged into state (LangGraph channel semantics).

The compiled graph records a *timeline* (node, ms, status) used by the
Traces app and emits ``agent.step`` events to the realtime hub.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("eaios.graph")

START = "__start__"
END = "__end__"

NodeFn = Callable[[dict], dict | None]
RouterFn = Callable[[dict], str]


@dataclass
class StateGraph:
    nodes: dict[str, NodeFn] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)                 # source → target
    branches: dict[str, RouterFn] = field(default_factory=dict)         # source → router(state) → target
    entry: str = ""

    def add_node(self, name: str, fn: NodeFn) -> "StateGraph":
        if name in (START, END):
            raise ValueError(f"'{name}' is reserved")
        self.nodes[name] = fn
        return self

    def add_edge(self, source: str, target: str) -> "StateGraph":
        if source == START:
            self.entry = target
        else:
            self.edges[source] = target
        return self

    def add_conditional_edges(self, source: str, router: RouterFn) -> "StateGraph":
        self.branches[source] = router
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        self.entry = name
        return self

    def compile(self) -> "CompiledGraph":  # noqa: A003
        if not self.entry:
            raise ValueError("Graph has no entry point")
        unknown = [t for t in self.edges.values() if t != END and t not in self.nodes]
        if unknown:
            raise ValueError(f"Edges point to unknown nodes: {unknown}")
        return CompiledGraph(self)


class CompiledGraph:
    def __init__(self, spec: StateGraph) -> None:
        self.spec = spec

    def invoke(self, state: dict, max_steps: int = 32, on_step: Callable[[str, str, int], None] | None = None) -> dict:
        """Run until END. ``on_step(node, phase, ms)`` fires around every node."""
        state = dict(state)
        state.setdefault("timeline", [])
        current = self.spec.entry
        steps = 0
        while current != END:
            if steps >= max_steps:
                raise RuntimeError(f"Graph exceeded {max_steps} steps (cycle?)")
            fn = self.spec.nodes.get(current)
            if fn is None:
                raise RuntimeError(f"Unknown node '{current}'")
            if on_step:
                on_step(current, "start", 0)
            t0 = time.perf_counter()
            status = "ok"
            try:
                update = fn(state)
            except Exception:
                status = "error"
                raise
            finally:
                ms = int((time.perf_counter() - t0) * 1000)
                state["timeline"].append({"node": current, "ms": ms, "status": status})
                if on_step:
                    on_step(current, "done", ms)
            if update:
                for key, value in update.items():
                    state[key] = value
            # conditional edges win over static edges (LangGraph precedence)
            if current in self.spec.branches:
                current = self.spec.branches[current](state)
            elif current in self.spec.edges:
                current = self.spec.edges[current]
            else:
                current = END
            steps += 1
        return state

    def describe(self) -> dict[str, Any]:
        """Static structure for UI visualization."""
        return {
            "entry": self.spec.entry,
            "nodes": list(self.spec.nodes),
            "edges": [{"from": s, "to": t} for s, t in self.spec.edges.items()],
            "conditional": list(self.spec.branches),
        }
