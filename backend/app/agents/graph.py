"""Graph-based orchestration runtime — LangGraph's StateGraph model,
implemented dependency-free so the platform always boots.

API surface mirrors ``langgraph.graph.StateGraph`` (add_node / add_edge /
add_conditional_edges / set_entry_point / compile → invoke), so swapping in
the real library is a one-line import change. State is a plain dict; each
node returns a partial dict merged into state (LangGraph channel semantics).

v2 additions (dynamic semantic routing support):

- **Channel reducers** — ``StateGraph(reducers={"answers": list_concat})``.
  For reduced keys, node updates are treated as *deltas* and combined with
  the existing value (LangGraph's ``Annotated[list, add]`` semantics). This
  makes node functions safe to run in parallel.
- **Fan-out** — a conditional-edge router may return a ``list`` of node
  names. Those branches execute **in parallel** (thread pool), each on a
  snapshot of the state; their delta-updates are reduced back in a
  deterministic order, then the graph converges on the branches' common
  next node (LangGraph's Send/join pattern).

The compiled graph records a *timeline* (node, ms, status, parallel flag)
used by the Traces app and emits ``agent.step`` events to the realtime hub.
"""
import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("eaios.graph")

START = "__start__"
END = "__end__"

NodeFn = Callable[[dict], dict | None]
RouterFn = Callable[[dict], "str | list[str]"]


def list_concat(old: Any, new: Any) -> list:
    """Default reducer for list channels: old + new (either may be missing)."""
    return [*(old or []), *(new or [])]


@dataclass
class StateGraph:
    nodes: dict[str, NodeFn] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)                 # source → target
    branches: dict[str, RouterFn] = field(default_factory=dict)         # source → router(state) → target(s)
    reducers: dict[str, Callable[[Any, Any], Any]] = field(default_factory=dict)
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

    # ── state helpers ────────────────────────────────────────────────────
    def _apply(self, state: dict, update: dict | None) -> None:
        if not update:
            return
        for key, value in update.items():
            reducer = self.spec.reducers.get(key)
            state[key] = reducer(state.get(key), value) if reducer else value

    def _next_of(self, node: str, state: dict) -> "str | list[str]":
        if node in self.spec.branches:
            return self.spec.branches[node](state)
        return self.spec.edges.get(node, END)

    def _run_node(self, name: str, state: dict,
                  on_step: Callable[[str, str, int], None] | None) -> tuple[dict | None, dict]:
        """Execute one node; returns (update, timeline_entry)."""
        fn = self.spec.nodes.get(name)
        if fn is None:
            raise RuntimeError(f"Unknown node '{name}'")
        if on_step:
            on_step(name, "start", 0)
        t0 = time.perf_counter()
        status = "ok"
        try:
            update = fn(state)
        except Exception:
            status = "error"
            raise
        finally:
            ms = int((time.perf_counter() - t0) * 1000)
            if on_step:
                on_step(name, "done", ms)
        return update, {"node": name, "ms": ms, "status": status}

    # ── execution ────────────────────────────────────────────────────────
    def invoke(self, state: dict, max_steps: int = 32,
               on_step: Callable[[str, str, int], None] | None = None) -> dict:
        """Run until END. ``on_step(node, phase, ms)`` fires around every node.

        Sequential by default; when a conditional edge returns a list of
        nodes, those branches run in parallel on state snapshots and their
        delta-updates are reduced back in list order.
        """
        state = dict(state)
        state.setdefault("timeline", [])
        current: str | list[str] = self.spec.entry
        steps = 0

        while current != END:
            if steps >= max_steps:
                raise RuntimeError(f"Graph exceeded {max_steps} steps (cycle?)")
            steps += 1

            # ── fan-out: parallel branches ──────────────────────────────
            if isinstance(current, list):
                targets = [t for t in current if t != END]
                if not targets:
                    break
                snapshot = dict(state)  # branches see identical pre-fan-out state
                with ThreadPoolExecutor(max_workers=min(len(targets), 8)) as pool:
                    futures = []
                    for t in targets:
                        ctx = contextvars.copy_context()  # propagate active trace into the thread
                        futures.append(pool.submit(ctx.run, self._run_node, t, dict(snapshot), on_step))
                    results = [f.result() for f in futures]  # raises on branch error

                for (update, entry), _name in zip(results, targets):
                    entry["parallel"] = True
                    state["timeline"].append(entry)
                    self._apply(state, update)

                # converge: all branches must agree on the next node
                nexts = {str(self._next_of(t, state)) for t in targets}
                raw_next = self._next_of(targets[0], state)
                if len(nexts) > 1:
                    raise RuntimeError(f"Parallel branches diverge: {nexts}")
                current = raw_next
                continue

            # ── sequential node ─────────────────────────────────────────
            update, entry = self._run_node(current, state, on_step)
            state["timeline"].append(entry)
            self._apply(state, update)
            current = self._next_of(current, state)

        return state

    def describe(self) -> dict[str, Any]:
        """Static structure for UI visualization."""
        return {
            "entry": self.spec.entry,
            "nodes": list(self.spec.nodes),
            "edges": [{"from": s, "to": t} for s, t in self.spec.edges.items()],
            "conditional": list(self.spec.branches),
            "reducers": list(self.spec.reducers),
        }
