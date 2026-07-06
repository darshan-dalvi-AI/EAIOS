"""Phase 2+ tests: graph orchestrator, realtime hub, knowledge graph,
workflows, and traces."""
import json

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _admin_headers(c: TestClient) -> dict:
    r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


def test_stategraph_engine():
    from app.agents.graph import END, START, StateGraph

    g = StateGraph()
    g.add_node("double", lambda s: {"value": s["value"] * 2})
    g.add_node("inc", lambda s: {"value": s["value"] + 1})
    g.add_edge(START, "double")
    g.add_conditional_edges("double", lambda s: "inc" if s["value"] < 10 else END)
    g.add_edge("inc", END)

    out = g.compile().invoke({"value": 3})
    assert out["value"] == 7  # 3*2=6 → <10 → +1
    assert [t["node"] for t in out["timeline"]] == ["double", "inc"]

    out = g.compile().invoke({"value": 6})
    assert out["value"] == 12  # 6*2=12 → END
    assert [t["node"] for t in out["timeline"]] == ["double"]


def test_chat_produces_trace_and_events():
    with client() as c:
        headers = _admin_headers(c)
        r = c.post("/api/chat", json={"message": "What is the leave policy?"}, headers=headers)
        assert r.status_code == 200

        # trace recorded with agent spans
        traces = c.get("/api/traces", headers=headers).json()
        assert len(traces) >= 1
        detail = c.get(f"/api/traces/{traces[0]['id']}", headers=headers).json()
        assert detail["kind"] == "chat"
        assert any(s["kind"] == "agent" for s in detail["spans"])

        # agent.step events replayable over REST
        events = c.get("/api/events/recent").json()
        assert any(e["type"] == "agent.step" and e["status"] == "done" for e in events)


def test_websocket_presence_and_auth():
    with client() as c:
        headers = _admin_headers(c)
        token = headers["Authorization"].removeprefix("Bearer ")

        with c.websocket_connect(f"/api/ws?token={token}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "presence"
            assert any(u["role"] == "admin" for u in msg["users"])

        # bad token rejected
        try:
            with c.websocket_connect("/api/ws?token=garbage") as ws:
                ws.receive_json()
            rejected = False
        except Exception:  # noqa: BLE001 — starlette raises on close code
            rejected = True
        assert rejected


def test_knowledge_graph_extraction_and_api():
    from app.services.kgraph import extract_entities

    ents = dict(extract_entities(
        "Maya Iyer from the Finance Department reviewed the Nimbus Cloud contract "
        "worth $48.2M in March. Contact maya@eaios.dev or the CISO."
    ))
    assert "Maya Iyer" in ents
    assert "maya@eaios.dev" in ents and ents["maya@eaios.dev"] == "person"
    assert any(k in ents for k in ("Finance Department", "Nimbus Cloud"))

    with client() as c:
        headers = _admin_headers(c)
        # seed a doc through upload so entities exist end-to-end
        r = c.post(
            "/api/documents/upload",
            files={"file": ("kg_test.txt", b"Maya Iyer manages the Nimbus Cloud contract. "
                                           b"Maya Iyer approved the Atlas Deployment with Nimbus Cloud support.")},
            headers=headers,
        )
        assert r.status_code == 201
        graph = c.get("/api/graph", headers=headers).json()
        names = [n["name"] for n in graph["nodes"]]
        assert "Maya Iyer" in names
        assert len(graph["edges"]) >= 1

        rel = c.get("/api/graph/relate", params={"a": "Maya Iyer", "b": "Nimbus Cloud"}, headers=headers)
        assert rel.status_code == 200
        assert rel.json()["connected"] is True


def test_workflow_crud_and_run():
    with client() as c:
        headers = _admin_headers(c)
        wf = {
            "name": "Test digest",
            "description": "t",
            "trigger": "manual",
            "nodes": [
                {"id": "t1", "type": "trigger", "x": 0, "y": 0, "data": {"label": "Manual"}},
                {"id": "a1", "type": "agent", "x": 0, "y": 0,
                 "data": {"label": "Summarize", "agent": "document", "prompt": "Summarize: {{input}}"}},
                {"id": "c1", "type": "condition", "x": 0, "y": 0, "data": {"label": "Gate", "contains": "leave"}},
                {"id": "n1", "type": "notify", "x": 0, "y": 0, "data": {"label": "Ping", "message": "done {{workflow}}"}},
            ],
            "edges": [{"from": "t1", "to": "a1"}, {"from": "a1", "to": "c1"}, {"from": "c1", "to": "n1"}],
            "enabled": True,
        }
        r = c.post("/api/workflows", json=wf, headers=headers)
        assert r.status_code == 201
        wf_id = r.json()["id"]

        r = c.post(f"/api/workflows/{wf_id}/run", json={"input": "annual leave policy"}, headers=headers)
        assert r.status_code == 200
        run = r.json()
        assert run["status"] == "ok"
        log = json.loads(run["log"])
        assert [e["type"] for e in log][:2] == ["trigger", "agent"]
        assert any(e["type"] == "condition" for e in log)

        r = c.get(f"/api/workflows/{wf_id}/runs", headers=headers)
        assert r.status_code == 200 and len(r.json()) == 1

        assert c.delete(f"/api/workflows/{wf_id}", headers=headers).status_code == 204


def test_orchestrator_graph_fallback_contract():
    """Even if the graph path exploded, the legacy path returns the same shape."""
    from app.agents.orchestrator import Orchestrator
    from app.core.database import SessionLocal
    from app.models import User

    with client() as c:  # ensures bootstrap admin exists
        c.get("/api/health")
    with SessionLocal() as db:
        user = db.query(User).first()
        orch = Orchestrator(db, user)
        result = orch._handle_legacy("What is the leave policy?", None)
        assert result.answer and 0 <= result.confidence <= 100
        graph_result = orch.handle("What is the leave policy?")
        assert graph_result.answer and graph_result.plan
        assert graph_result.timeline, "graph path records a node timeline"
