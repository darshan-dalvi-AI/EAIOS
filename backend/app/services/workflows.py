"""Workflow engine — executes visual automations built in the Automations app.

A workflow is a small DAG stored as JSON:
    nodes: [{id, type, x, y, data}]   type ∈ trigger | agent | condition | approve | notify
    edges: [{from, to}]

Execution walks the DAG from the trigger node; each node transforms `payload`
(the running text) and appends a log entry. Agent nodes call the same
specialist agents the chat orchestrator uses — one runtime, two front doors.
Runs are traced (Traces app) and streamed to the realtime hub.

**Human-in-the-Loop (approve node):** when the walk reaches an ``approve``
node, execution PAUSES. The remaining queue, payload, logs and context are
checkpointed onto the WorkflowRun (status ``awaiting_approval``) and a live
event asks an admin to approve. ``resume()`` reloads the checkpoint and
continues (or aborts on reject) — a lightweight LangGraph-style checkpointer
that survives process restarts because state lives in the database.
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


def _walk(db: Session, wf: Workflow, run: WorkflowRun, user: User | None,
          queue: list, payload: str, logs: list, context: dict, steps: int) -> WorkflowRun:
    """Core DAG walk. Runs until the queue empties or an approve node pauses
    it; persists the result either way."""
    nodes = {n["id"]: n for n in json.loads(wf.nodes or "[]")}
    downstream: dict[str, list[str]] = {}
    for e in json.loads(wf.edges or "[]"):
        downstream.setdefault(e["from"], []).append(e["to"])

    t0 = time.perf_counter()
    prior_ms = run.duration_ms or 0
    status = "ok"
    paused = False

    try:
        if len(nodes) > MAX_NODES:
            raise ValueError(f"Workflow exceeds {MAX_NODES} nodes")

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

            # ── Human-in-the-Loop pause ─────────────────────────────────
            if ntype == "approve":
                logs.append({"node": node_id, "type": "approve", "label": label,
                             "status": "awaiting", "ms": 0,
                             "output": f"⏸ Waiting for admin approval — {data.get('message', 'approve to continue')}"})
                # checkpoint the remaining work (this node's children fire on approval)
                run.pending = json.dumps({
                    "resume_queue": [(c, incoming) for c in downstream.get(node_id, [])],
                    "payload": incoming, "logs": logs, "context": context, "steps": steps,
                })
                run.status = "awaiting_approval"
                run.log = json.dumps(logs)
                run.duration_ms = prior_ms + int((time.perf_counter() - t0) * 1000)
                db.commit()
                db.refresh(run)
                hub.publish("workflow.approval", workflow=wf.name, run_id=run.id,
                            message=_render(data.get("message", "Approval required for '{{workflow}}'"), incoming, context)[:300])
                paused = True
                break

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

    if paused:
        end_trace("ok")
        return run

    run.status = status
    run.output = payload[:4000]
    run.log = json.dumps(logs)
    run.pending = ""
    run.duration_ms = prior_ms + int((time.perf_counter() - t0) * 1000)
    db.commit()
    db.refresh(run)
    end_trace(status)
    hub.publish("workflow.run", workflow=wf.name, status=status, ms=run.duration_ms)
    return run


def execute(db: Session, wf: Workflow, input_text: str, trigger: str, actor: User | None = None) -> WorkflowRun:
    """Run a workflow synchronously; returns the persisted WorkflowRun.
    May return with status ``awaiting_approval`` if it hits an approve node."""
    user = actor or db.get(User, wf.owner_id)
    nodes = {n["id"]: n for n in json.loads(wf.nodes or "[]")}

    run = WorkflowRun(workflow_id=wf.id, status="running", trigger=trigger, input=input_text[:2000])
    db.add(run)
    db.commit()
    db.refresh(run)

    hub.publish("workflow.run", workflow=wf.name, status="start", trigger=trigger)
    start_trace(f"workflow: {wf.name}", user=user.email if user else "", kind="workflow")

    context = {"trigger": trigger, "workflow": wf.name, "date": _now().date().isoformat()}
    starts = [n["id"] for n in nodes.values() if n["type"] == "trigger"] or list(nodes)[:1]
    queue = [(nid, input_text) for nid in starts]

    wf.run_count = (wf.run_count or 0) + 1
    wf.last_run_at = _now()
    db.commit()
    return _walk(db, wf, run, user, queue, input_text, [], context, 0)


def resume(db: Session, run: WorkflowRun, approved: bool, actor: User | None = None) -> WorkflowRun:
    """Continue a paused (HITL) run after an admin approves or rejects it."""
    if run.status != "awaiting_approval" or not run.pending:
        return run
    wf = db.get(Workflow, run.workflow_id)
    user = actor or (db.get(User, wf.owner_id) if wf else None)
    state = json.loads(run.pending)
    logs = state["logs"]

    if not approved:
        logs.append({"node": "-", "type": "approve", "label": "rejected", "status": "error",
                     "ms": 0, "output": f"✗ Rejected by {actor.full_name if actor else 'admin'} — run halted."})
        run.status = "error"
        run.log = json.dumps(logs)
        run.pending = ""
        db.commit()
        db.refresh(run)
        hub.publish("workflow.run", workflow=wf.name if wf else "?", status="rejected", ms=run.duration_ms)
        return run

    logs.append({"node": "-", "type": "approve", "label": "approved", "status": "ok",
                 "ms": 0, "output": f"✓ Approved by {actor.full_name if actor else 'admin'} — resuming."})
    run.status = "running"
    db.commit()
    start_trace(f"workflow (resumed): {wf.name}", user=user.email if user else "", kind="workflow")
    queue = [tuple(item) for item in state["resume_queue"]]
    return _walk(db, wf, run, user, queue, state["payload"], logs, state["context"], state["steps"])


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


# ── scheduled workflows ──────────────────────────────────────────────────
def _interval_minutes(wf: Workflow) -> int:
    """Interval comes from the trigger node's config: {"every": <minutes>}.
    Defaults to 60 and is clamped to ≥ 1 minute."""
    try:
        for node in json.loads(wf.nodes or "[]"):
            if node.get("type") == "trigger":
                return max(1, int(float(node.get("data", {}).get("every") or 60)))
    except Exception:  # noqa: BLE001
        pass
    return 60


def run_due_scheduled(db: Session, now: datetime | None = None) -> int:
    """Fire every enabled `trigger=schedule` workflow whose interval has
    elapsed since its last run. Called by the app's scheduler loop."""
    now = now or _now()
    fired = 0
    for wf in db.scalars(select(Workflow).where(Workflow.trigger == "schedule", Workflow.enabled == True)).all():  # noqa: E712
        minutes = _interval_minutes(wf)
        last = wf.last_run_at
        if last is not None and last.tzinfo is None:  # SQLite returns naive datetimes
            last = last.replace(tzinfo=timezone.utc)
        if last is not None and (now - last).total_seconds() < minutes * 60:
            continue
        try:
            execute(db, wf, f"Scheduled run · every {minutes} min · {now.isoformat(timespec='minutes')}",
                    trigger="schedule")
            fired += 1
        except Exception:  # noqa: BLE001
            log.exception("scheduled workflow %s failed", wf.id)
    return fired
