"""Workflow engine — executes visual automations built in the Automations app.

A workflow is a small DAG stored as JSON:
    nodes: [{id, type, x, y, data}]   type ∈ trigger | agent | condition | notify
    edges: [{from, to}]

Execution walks the DAG from the trigger node; each node transforms `payload`
(the running text) and appends a log entry. Agent nodes call the same
specialist agents the chat orchestrator uses — one runtime, two front doors.
Runs are traced (Traces app) and streamed to the realtime hub.
"""
import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import AGENT_MAP
from app.core.events import hub
from app.core.tracing import end_trace, span, start_trace
from app.models import User, Workflow, WorkflowRun

log = logging.getLogger("eaios.workflows")

MAX_NODES = 24
MAX_STEPS = 40


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _render(template: str, payload: str, context: dict) -> str:
    out = template or "{{input}}"
    out = out.replace("{{input}}", payload)
    for key, value in context.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def execute(db: Session, wf: Workflow, input_text: str, trigger: str, actor: User | None = None) -> WorkflowRun:
    """Run a workflow synchronously; returns the persisted WorkflowRun."""
    user = actor or db.get(User, wf.owner_id)
    nodes = {n["id"]: n for n in json.loads(wf.nodes or "[]")}
    edges = json.loads(wf.edges or "[]")
    downstream: dict[str, list[str]] = {}
    for e in edges:
        downstream.setdefault(e["from"], []).append(e["to"])

    run = WorkflowRun(workflow_id=wf.id, status="running", trigger=trigger, input=input_text[:2000])
    db.add(run)
    db.commit()
    db.refresh(run)

    hub.publish("workflow.run", workflow=wf.name, status="start", trigger=trigger)
    start_trace(f"workflow: {wf.name}", user=user.email if user else "", kind="workflow")

    t0 = time.perf_counter()
    logs: list[dict] = []
    status = "ok"
    payload = input_text
    context = {"trigger": trigger, "workflow": wf.name, "date": _now().date().isoformat()}

    try:
        if len(nodes) > MAX_NODES:
            raise ValueError(f"Workflow exceeds {MAX_NODES} nodes")
        starts = [n["id"] for n in nodes.values() if n["type"] == "trigger"] or list(nodes)[:1]
        queue: list[tuple[str, str]] = [(nid, payload) for nid in starts]
        steps = 0

        while queue:
            if steps >= MAX_STEPS:
                raise RuntimeError(f"Workflow exceeded {MAX_STEPS} steps")
            steps += 1
            node_id, incoming = queue.pop(0)
            node = nodes.get(node_id)
            if node is None:
                continue
            ntype = node.get("type", "agent")
            data = node.get("data", {}) or {}
            label = data.get("label") or ntype
            entry = {"node": node_id, "type": ntype, "label": label, "status": "ok", "ms": 0, "output": ""}
            nt0 = time.perf_counter()
            proceed = True
            outgoing = incoming

            try:
                if ntype == "trigger":
                    entry["output"] = incoming[:400]
                elif ntype == "agent":
                    agent_id = data.get("agent", "document")
                    if agent_id not in AGENT_MAP or agent_id == "planning":
                        raise ValueError(f"Unknown agent '{agent_id}'")
                    task = _render(data.get("prompt", ""), incoming, context)
                    agent = AGENT_MAP[agent_id](db, user)
                    hub.publish("agent.step", agent=agent_id, status="start",
                                task=f"workflow · {wf.name}", user=(user.full_name if user else "system"))
                    with span(f"{label} ({agent_id})", kind="agent", workflow=wf.name):
                        result = agent.run(task)
                    hub.publish("agent.step", agent=agent_id, status="done",
                                task=f"workflow · {wf.name}", user=(user.full_name if user else "system"),
                                confidence=result.confidence)
                    outgoing = result.answer
                    entry["output"] = result.answer[:400]
                elif ntype == "condition":
                    needle = (data.get("contains") or "").lower()
                    proceed = bool(needle) and needle in incoming.lower()
                    entry["output"] = f"contains '{needle}' → {proceed}"
                elif ntype == "notify":
                    message = _render(data.get("message", "Workflow '{{workflow}}' finished."), incoming, context)
                    hub.publish("workflow.notify", workflow=wf.name, message=message[:300])
                    entry["output"] = message[:400]
                else:
                    entry["output"] = f"skipped unknown type '{ntype}'"
            except Exception as exc:  # noqa: BLE001
                entry["status"] = "error"
                entry["output"] = str(exc)[:300]
                status = "error"
                proceed = False

            entry["ms"] = int((time.perf_counter() - nt0) * 1000)
            logs.append(entry)
            payload = outgoing
            if proceed:
                queue.extend((child, outgoing) for child in downstream.get(node_id, []))

    except Exception as exc:  # noqa: BLE001
        status = "error"
        logs.append({"node": "-", "type": "engine", "label": "engine", "status": "error",
                     "ms": 0, "output": str(exc)[:300]})

    run.status = status
    run.output = payload[:4000]
    run.log = json.dumps(logs)
    run.duration_ms = int((time.perf_counter() - t0) * 1000)
    wf.run_count = (wf.run_count or 0) + 1
    wf.last_run_at = _now()
    db.commit()
    db.refresh(run)

    end_trace(status)
    hub.publish("workflow.run", workflow=wf.name, status=status, ms=run.duration_ms)
    return run


def fire_trigger(db: Session, trigger: str, input_text: str) -> int:
    """Run every enabled workflow bound to `trigger` (e.g. document upload)."""
    fired = 0
    for wf in db.scalars(select(Workflow).where(Workflow.trigger == trigger, Workflow.enabled == True)).all():  # noqa: E712
        try:
            execute(db, wf, input_text, trigger=trigger)
            fired += 1
        except Exception:  # noqa: BLE001
            log.exception("workflow %s failed on trigger %s", wf.id, trigger)
    return fired
