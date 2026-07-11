"""LangGraph-style checkpointer — per-super-step state persistence + resume."""
from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient) -> dict:
    r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


def test_interrupted_graph_resumes_from_saved_node():
    from app.agents.checkpointer import MemoryCheckpointer
    from app.agents.graph import END, START, StateGraph, list_concat

    calls = {"a": 0, "b": 0}
    boom = {"armed": True}

    def node_a(state):
        calls["a"] += 1
        return {"out": ["a"]}

    def node_b(state):
        if boom.pop("armed", False):
            raise RuntimeError("simulated LLM outage")
        calls["b"] += 1
        return {"out": ["b"]}

    g = StateGraph(reducers={"out": list_concat})
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)

    cp = MemoryCheckpointer()
    compiled = g.compile(checkpointer=cp)

    # first run dies at node b — checkpoint marks the interruption
    try:
        compiled.invoke({"text": "crunch the numbers"}, thread_id="th-1")
        raise AssertionError("expected simulated failure")
    except RuntimeError:
        pass
    saved = cp.get("th-1")
    assert saved["status"] == "interrupted"
    assert saved["next"] == "b"
    assert saved["state"]["out"] == ["a"]

    # retrying the SAME request on the SAME thread resumes at b — a is NOT re-run
    out = compiled.invoke({"text": "crunch the numbers"}, thread_id="th-1")
    assert calls == {"a": 1, "b": 1}
    assert out["out"] == ["a", "b"]
    assert any(t["node"] == "__resume__" for t in out["timeline"])
    assert cp.get("th-1")["status"] == "done"

    # a DIFFERENT request on that thread starts fresh (no stale resume)
    boom.clear()
    out2 = compiled.invoke({"text": "something else"}, thread_id="th-1")
    assert calls["a"] == 2
    assert out2["out"] == ["a", "b"]


def test_db_checkpointer_roundtrip_rehydrates_rich_state():
    from app.agents.checkpointer import DBCheckpointer
    from app.agents.orchestrator import checkpoint_dumps, checkpoint_loads
    from app.core.database import init_db
    from app.schemas import Citation

    init_db()
    cp = DBCheckpointer(dumps=checkpoint_dumps, loads=checkpoint_loads)
    state = {
        "text": "quarterly numbers",
        "citations": [Citation(doc_id="d1", title="Q3 Report", section="Revenue", score=0.91)],
        "queue": [("sql", "count users")],
        "answers": ["partial"],
    }
    cp.put("th-db-1", state, ["document", "sql"], status="interrupted")

    got = cp.get("th-db-1")
    assert got["status"] == "interrupted"
    assert got["next"] == ["document", "sql"]
    assert isinstance(got["state"]["citations"][0], Citation)
    assert got["state"]["citations"][0].title == "Q3 Report"
    assert got["state"]["queue"] == [("sql", "count users")]

    cp.done("th-db-1", got["state"])
    assert cp.get("th-db-1")["status"] == "done"
    assert cp.get("th-db-1")["steps"] >= 2


def test_chat_persists_done_checkpoint_per_conversation():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/chat", json={"message": "What is the leave policy?"}, headers=h)
        assert r.status_code == 200
        conv_id = r.json()["conversation_id"]

        from app.core.database import SessionLocal
        from app.models import GraphCheckpoint

        with SessionLocal() as db:
            row = db.query(GraphCheckpoint).filter(GraphCheckpoint.thread_id == conv_id).first()
            assert row is not None, "chat run should checkpoint its graph state"
            assert row.status == "done"
            assert row.steps >= 2  # router + agent(s) + merge
