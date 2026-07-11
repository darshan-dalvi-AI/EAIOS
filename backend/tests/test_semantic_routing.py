"""Dynamic semantic routing: JSON validation, engine fan-out, e2e parallel chat."""
import threading
import time

from fastapi.testclient import TestClient

from app.agents import orchestrator as orch
from app.agents.graph import END, START, StateGraph, list_concat
from app.agents.orchestrator import parse_router_json
from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _admin_headers(c: TestClient) -> dict:
    r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


# ── router JSON validation ───────────────────────────────────────────────
def test_parse_router_json_happy_path():
    raw = 'Sure! {"tasks": [{"agent": "document", "task": "Find leave policy"}, {"agent": "email", "task": "Draft HR email"}]}'
    assert parse_router_json(raw) == [("document", "Find leave policy"), ("email", "Draft HR email")]


def test_parse_router_json_filters_and_merges():
    raw = ('{"tasks": ['
           '{"agent": "hacker", "task": "bad"},'          # unknown agent → dropped
           '{"agent": "planning", "task": "meta"},'        # planning not routable → dropped
           '{"agent": "sql", "task": "count users"},'
           '{"agent": "sql", "task": "count documents"},'  # duplicate agent → merged
           '{"agent": "coding", "task": ""}]}')            # empty task → dropped
    assert parse_router_json(raw) == [("sql", "count users Also: count documents")]


def test_parse_router_json_garbage_returns_none():
    assert parse_router_json("I think you should use the document agent!") is None
    assert parse_router_json('{"tasks": []}') is None
    assert parse_router_json('{"tasks": "document"}') is None


# ── engine fan-out ───────────────────────────────────────────────────────
def test_stategraph_parallel_fanout_with_reducers():
    seen = []

    def make(name, delay):
        def fn(state):
            time.sleep(delay)
            seen.append((name, threading.get_ident()))
            return {"answers": [name]}
        return fn

    g = StateGraph(reducers={"answers": list_concat})
    g.add_node("router", lambda s: None)
    g.add_node("a", make("a", 0.15))
    g.add_node("b", make("b", 0.15))
    g.add_node("merge", lambda s: {"joined": "+".join(s["answers"])})
    g.add_edge(START, "router")
    g.add_conditional_edges("router", lambda s: ["a", "b"])
    g.add_conditional_edges("a", lambda s: "merge")
    g.add_conditional_edges("b", lambda s: "merge")
    g.add_edge("merge", END)

    t0 = time.perf_counter()
    out = g.compile().invoke({})
    elapsed = time.perf_counter() - t0

    assert sorted(out["answers"]) == ["a", "b"]
    assert out["joined"] in ("a+b", "b+a")
    assert elapsed < 0.27, f"branches did not run in parallel ({elapsed:.2f}s)"
    assert len({tid for _, tid in seen}) == 2, "expected two worker threads"
    parallel_entries = [t for t in out["timeline"] if t.get("parallel")]
    assert {t["node"] for t in parallel_entries} == {"a", "b"}


# ── end-to-end: LLM-routed parallel chat ─────────────────────────────────
def test_chat_with_semantic_router_parallel(monkeypatch):
    monkeypatch.setattr(
        orch, "semantic_route",
        lambda text: [("document", "How many annual leave days do employees get?"),
                      ("email", "Draft an email to HR about carrying over leave days.")],
    )
    with client() as c:
        headers = _admin_headers(c)
        r = c.post("/api/chat", json={"message": "leave days + email HR please"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["plan"][0] == "router"
        assert set(body["plan"][1:]) == {"document", "email"}
        content = body["message"]["content"]
        assert "Document Agent" in content and "Email Agent" in content
        assert body["message"]["agent"] == "planning"  # multi-agent merge


def test_mock_provider_keeps_regex_routing():
    """auto mode + mock LLM → deterministic regex path (no router chip)."""
    with client() as c:
        headers = _admin_headers(c)
        r = c.post("/api/chat", json={"message": "How many users are in the database?"}, headers=headers)
        assert r.status_code == 200
        plan = r.json()["plan"]
        assert "router" not in plan
        assert "sql" in plan
