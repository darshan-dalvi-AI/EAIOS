/* Automations — visual workflow builder.
   Hand-rolled node canvas (drag nodes, click-port-to-connect bezier edges) —
   no diagram library, so it stays true to the Aurora design system and the
   single-file demo build. Workflows execute on the backend agent runtime;
   demo mode simulates the same walk client-side. */
import {
  Bell, Bot, CirclePlay, GitFork, Play, Plus, Save, Trash2, Workflow as WorkflowIcon, Zap,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiDeleteWorkflow, apiRunWorkflow, apiSaveWorkflow, apiWorkflows } from "../lib/api";
import { AGENTS } from "../lib/mock";
import type { WfNode, WfNodeType, WorkflowDef, WorkflowRunInfo } from "../types";

const NODE_W = 170;
const NODE_H = 58;

const NODE_STYLE: Record<WfNodeType, { hue: number; Icon: typeof Zap; title: string }> = {
  trigger: { hue: 95, Icon: Zap, title: "Trigger" },
  agent: { hue: 265, Icon: Bot, title: "Agent" },
  condition: { hue: 38, Icon: GitFork, title: "Condition" },
  notify: { hue: 320, Icon: Bell, title: "Notify" },
};

const AGENT_OPTIONS = AGENTS.filter((a) => a.id !== "planning").map((a) => ({ id: a.id, name: a.name }));

function newWorkflow(): WorkflowDef {
  return {
    id: `new-${Date.now()}`,
    name: "Untitled automation",
    description: "",
    trigger: "manual",
    enabled: true,
    run_count: 0,
    last_run_at: null,
    nodes: [
      { id: "n1", type: "trigger", x: 60, y: 140, data: { label: "Manual" } },
      { id: "n2", type: "agent", x: 330, y: 140, data: { label: "Answer", agent: "document", prompt: "{{input}}" } },
    ],
    edges: [{ from: "n1", to: "n2" }],
  };
}

export default function AutomationsApp() {
  const [list, setList] = useState<WorkflowDef[]>([]);
  const [wf, setWf] = useState<WorkflowDef | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [run, setRun] = useState<WorkflowRunInfo | null>(null);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runInput, setRunInput] = useState("Summarize the leave policy");
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiWorkflows().then((ws) => {
      setList(ws);
      if (ws.length > 0) setWf(structuredClone(ws[0]));
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setConnecting(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const patchNode = (id: string, patch: Partial<WfNode["data"]>) =>
    setWf((w) => w && ({
      ...w,
      nodes: w.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)),
    }));

  const addNode = (type: WfNodeType) => {
    if (!wf) return;
    const id = `n${Date.now() % 100000}`;
    const defaults: WfNode["data"] =
      type === "agent" ? { label: "New agent", agent: "document", prompt: "{{input}}" }
      : type === "condition" ? { label: "Check", contains: "" }
      : type === "notify" ? { label: "Notify", message: "Workflow {{workflow}} finished" }
      : { label: "Trigger" };
    setWf({ ...wf, nodes: [...wf.nodes, { id, type, x: 120 + Math.random() * 320, y: 80 + Math.random() * 260, data: defaults }] });
    setSelectedNode(id);
  };

  const removeNode = (id: string) =>
    setWf((w) => w && ({
      ...w,
      nodes: w.nodes.filter((n) => n.id !== id),
      edges: w.edges.filter((e) => e.from !== id && e.to !== id),
    }));

  const connectTo = (targetId: string) => {
    if (!wf || !connecting || connecting === targetId) { setConnecting(null); return; }
    const exists = wf.edges.some((e) => e.from === connecting && e.to === targetId);
    if (!exists) setWf({ ...wf, edges: [...wf.edges, { from: connecting, to: targetId }] });
    setConnecting(null);
  };

  // ── node dragging ──
  const onNodeDown = (e: React.PointerEvent, node: WfNode) => {
    if ((e.target as HTMLElement).closest("[data-port]")) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    dragRef.current = { id: node.id, dx: node.x - (e.clientX - rect.left), dy: node.y - (e.clientY - rect.top) };
    setSelectedNode(node.id);
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onCanvasMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || !wf) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = Math.max(4, e.clientX - rect.left + drag.dx);
    const y = Math.max(4, e.clientY - rect.top + drag.dy);
    setWf({ ...wf, nodes: wf.nodes.map((n) => (n.id === drag.id ? { ...n, x, y } : n)) });
  };
  const onCanvasUp = () => { dragRef.current = null; };

  // ── persistence + execution ──
  const save = async () => {
    if (!wf) return;
    setSaving(true);
    try {
      const saved = await apiSaveWorkflow(wf);
      setWf(structuredClone(saved));
      setList((ls) => {
        const i = ls.findIndex((w) => w.id === saved.id || w.id === wf.id);
        if (i >= 0) return ls.map((w, j) => (j === i ? saved : w));
        return [saved, ...ls];
      });
    } finally {
      setSaving(false);
    }
  };

  const execute = async () => {
    if (!wf) return;
    setRunning(true);
    setRun(null);
    try {
      if (wf.id.startsWith("new-")) await save();
      const current = wf.id.startsWith("new-") ? (await apiWorkflows())[0] : wf;
      setRun(await apiRunWorkflow(current.id, runInput));
    } catch (err) {
      setRun({
        id: "err", status: "error", trigger: "manual", input: runInput,
        output: err instanceof Error ? err.message : "Run failed", log: [], duration_ms: 0,
        created_at: new Date().toISOString(),
      });
    } finally {
      setRunning(false);
    }
  };

  const removeWorkflow = async (id: string) => {
    await apiDeleteWorkflow(id);
    setList((ls) => ls.filter((w) => w.id !== id));
    if (wf?.id === id) setWf(null);
  };

  const selected = wf?.nodes.find((n) => n.id === selectedNode) ?? null;
  const port = (n: WfNode, side: "in" | "out") => ({
    x: n.x + (side === "out" ? NODE_W : 0),
    y: n.y + NODE_H / 2,
  });

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      {/* ── left: workflow list ── */}
      <aside className="app-sidebar" style={{ width: 208, padding: "12px 10px" }}>
        <button className="btn sm primary" style={{ width: "100%", justifyContent: "center", marginBottom: 10 }}
          onClick={() => { const w = newWorkflow(); setWf(w); setSelectedNode(null); setRun(null); }}>
          <Plus size={13} /> New automation
        </button>
        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
          {list.map((w) => (
            <div key={w.id} className={`card hover ${wf?.id === w.id ? "selected" : ""}`}
              style={{ padding: "8px 10px", cursor: "pointer", borderColor: wf?.id === w.id ? "var(--accent)" : undefined }}
              onClick={() => { setWf(structuredClone(w)); setSelectedNode(null); setRun(null); }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <WorkflowIcon size={13} style={{ color: "#a3e635", flexShrink: 0 }} />
                <span style={{ fontSize: 12.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.name}</span>
              </div>
              <div style={{ display: "flex", gap: 5, marginTop: 6, alignItems: "center" }}>
                <span className="pill dim">{w.trigger}</span>
                <span className="faint" style={{ fontSize: 10.5 }}>{w.run_count} runs</span>
                <button className="btn sm" style={{ marginLeft: "auto", padding: "2px 5px" }} title="Delete"
                  onClick={(e) => { e.stopPropagation(); removeWorkflow(w.id); }}>
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          ))}
          {list.length === 0 && <p className="faint" style={{ fontSize: 11.5 }}>No automations yet.</p>}
        </div>
      </aside>

      {/* ── center: canvas ── */}
      <div className="app-pane">
        {wf ? (
          <>
            <div className="app-toolbar" style={{ gap: 8 }}>
              <input className="input sm" style={{ width: 190, fontWeight: 600 }} value={wf.name}
                onChange={(e) => setWf({ ...wf, name: e.target.value })} />
              <select className="input sm" value={wf.trigger}
                onChange={(e) => setWf({ ...wf, trigger: e.target.value as WorkflowDef["trigger"] })}>
                <option value="manual">manual</option>
                <option value="upload">on upload</option>
                <option value="schedule">schedule</option>
              </select>
              {(Object.keys(NODE_STYLE) as WfNodeType[]).map((t) => {
                const { Icon, hue, title } = NODE_STYLE[t];
                return (
                  <button key={t} className="btn sm" title={`Add ${title} node`} onClick={() => addNode(t)}>
                    <Icon size={12} style={{ color: `hsl(${hue}, 85%, 65%)` }} /> {title}
                  </button>
                );
              })}
              <span style={{ marginLeft: "auto" }} />
              <button className="btn sm" onClick={save} disabled={saving}>
                <Save size={12} /> {saving ? "Saving…" : "Save"}
              </button>
              <button className="btn sm primary" onClick={execute} disabled={running}>
                <Play size={12} /> {running ? "Running…" : "Run"}
              </button>
            </div>

            {connecting && (
              <div style={{ padding: "4px 12px", fontSize: 11.5, color: "var(--accent)", borderBottom: "1px solid var(--hairline)" }}>
                Connecting from <b>{wf.nodes.find((n) => n.id === connecting)?.data.label}</b> — click a target node (Esc to cancel)
              </div>
            )}

            <div
              ref={canvasRef}
              className="app-content"
              style={{ position: "relative", overflow: "auto", padding: 0, backgroundImage: "radial-gradient(circle, rgba(148,163,184,0.13) 1px, transparent 1px)", backgroundSize: "22px 22px" }}
              onPointerMove={onCanvasMove}
              onPointerUp={onCanvasUp}
              onClick={() => { setSelectedNode(null); setConnecting(null); }}
            >
              <svg width="1400" height="760" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
                {wf.edges.map((e, i) => {
                  const a = wf.nodes.find((n) => n.id === e.from);
                  const b = wf.nodes.find((n) => n.id === e.to);
                  if (!a || !b) return null;
                  const p1 = port(a, "out"), p2 = port(b, "in");
                  const mx = (p1.x + p2.x) / 2;
                  return (
                    <g key={i}>
                      <path d={`M ${p1.x} ${p1.y} C ${mx} ${p1.y}, ${mx} ${p2.y}, ${p2.x} ${p2.y}`}
                        fill="none" stroke="hsla(190, 90%, 60%, 0.55)" strokeWidth={1.8} />
                      <circle cx={p2.x - 3} cy={p2.y} r={3} fill="hsl(190, 90%, 60%)" />
                    </g>
                  );
                })}
              </svg>

              {wf.nodes.map((n) => {
                const { hue, Icon } = NODE_STYLE[n.type];
                const isSel = selectedNode === n.id;
                return (
                  <div
                    key={n.id}
                    onPointerDown={(e) => onNodeDown(e, n)}
                    onClick={(e) => { e.stopPropagation(); if (connecting) connectTo(n.id); else setSelectedNode(n.id); }}
                    style={{
                      position: "absolute", left: n.x, top: n.y, width: NODE_W, height: NODE_H,
                      borderRadius: 12, padding: "8px 12px", cursor: "grab", userSelect: "none",
                      background: `linear-gradient(145deg, hsla(${hue}, 60%, 24%, 0.55), hsla(${hue}, 60%, 14%, 0.7))`,
                      border: `1px solid ${isSel || connecting === n.id ? `hsl(${hue}, 90%, 62%)` : "var(--hairline)"}`,
                      boxShadow: isSel ? `0 0 18px hsla(${hue}, 90%, 60%, 0.25)` : "0 4px 14px rgba(0,0,0,0.35)",
                      backdropFilter: "blur(6px)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <Icon size={13} style={{ color: `hsl(${hue}, 85%, 65%)`, flexShrink: 0 }} />
                      <span style={{ fontSize: 12.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {n.data.label || NODE_STYLE[n.type].title}
                      </span>
                    </div>
                    <div className="faint" style={{ fontSize: 10.5, marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {n.type === "agent" ? `→ ${AGENT_OPTIONS.find((a) => a.id === n.data.agent)?.name ?? n.data.agent}`
                        : n.type === "condition" ? `contains “${n.data.contains || "…"}”`
                        : n.type === "notify" ? n.data.message
                        : wf.trigger}
                    </div>
                    {/* ports */}
                    {n.type !== "trigger" && (
                      <span data-port="in" title="Input"
                        style={{ position: "absolute", left: -5, top: NODE_H / 2 - 5, width: 10, height: 10, borderRadius: 10, background: "var(--surface-solid, #111)", border: "1.5px solid hsla(190,90%,60%,0.8)" }} />
                    )}
                    <span
                      data-port="out"
                      title="Drag target: click to start a connection"
                      onClick={(e) => { e.stopPropagation(); setConnecting(n.id); }}
                      style={{ position: "absolute", right: -5, top: NODE_H / 2 - 5, width: 10, height: 10, borderRadius: 10, cursor: "crosshair", background: connecting === n.id ? "hsl(190,90%,60%)" : "var(--surface-solid, #111)", border: "1.5px solid hsla(190,90%,60%,0.8)" }} />
                  </div>
                );
              })}
            </div>

            {/* ── run console ── */}
            <div style={{ borderTop: "1px solid var(--hairline)", padding: "8px 12px", maxHeight: 190, overflowY: "auto" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <CirclePlay size={13} style={{ color: "var(--accent)" }} />
                <input className="input sm" style={{ flex: 1 }} placeholder="Run input… ({{input}} in agent prompts)"
                  value={runInput} onChange={(e) => setRunInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && execute()} />
                {run && (
                  <span className={`pill ${run.status === "ok" ? "good" : "warn"}`}>
                    {run.status} · {run.duration_ms} ms
                  </span>
                )}
              </div>
              {running && <p className="faint" style={{ fontSize: 11.5, margin: "8px 0 0" }}>Walking the graph…</p>}
              {run && run.log.map((l, i) => (
                <div key={i} className="feed-item" style={{ alignItems: "flex-start" }}>
                  <span className={`pill ${l.status === "ok" ? "dim" : "warn"}`} style={{ flexShrink: 0 }}>{l.label}</span>
                  <span className="muted" style={{ fontSize: 11.5, whiteSpace: "pre-wrap" }}>
                    {l.output.slice(0, 220)}{l.output.length > 220 ? "…" : ""} <span className="faint">({l.ms} ms)</span>
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="empty">
            <WorkflowIcon size={26} style={{ opacity: 0.5 }} />
            <div>Pick an automation or create a new one — build “on upload → summarize → notify” visually.</div>
          </div>
        )}
      </div>

      {/* ── right: node inspector ── */}
      {wf && selected && (
        <aside className="app-sidebar" style={{ width: 240, borderRight: "none", borderLeft: "1px solid var(--hairline)", padding: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <h3 className="h-display" style={{ fontSize: 13.5, margin: 0 }}>{NODE_STYLE[selected.type].title} node</h3>
            <button className="btn sm" style={{ marginLeft: "auto" }} title="Delete node"
              onClick={() => { removeNode(selected.id); setSelectedNode(null); }}>
              <Trash2 size={12} />
            </button>
          </div>
          <label className="faint" style={{ fontSize: 11, display: "block", margin: "12px 0 4px" }}>Label</label>
          <input className="input sm" style={{ width: "100%" }} value={selected.data.label ?? ""}
            onChange={(e) => patchNode(selected.id, { label: e.target.value })} />

          {selected.type === "agent" && (
            <>
              <label className="faint" style={{ fontSize: 11, display: "block", margin: "12px 0 4px" }}>Agent</label>
              <select className="input sm" style={{ width: "100%" }} value={selected.data.agent ?? "document"}
                onChange={(e) => patchNode(selected.id, { agent: e.target.value })}>
                {AGENT_OPTIONS.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              <label className="faint" style={{ fontSize: 11, display: "block", margin: "12px 0 4px" }}>
                Prompt — <code style={{ fontSize: 10 }}>{"{{input}}"}</code> = upstream output
              </label>
              <textarea className="input sm" rows={5} style={{ width: "100%", resize: "vertical", fontFamily: "var(--mono, monospace)", fontSize: 11.5 }}
                value={selected.data.prompt ?? ""} onChange={(e) => patchNode(selected.id, { prompt: e.target.value })} />
            </>
          )}
          {selected.type === "condition" && (
            <>
              <label className="faint" style={{ fontSize: 11, display: "block", margin: "12px 0 4px" }}>Continue only if output contains</label>
              <input className="input sm" style={{ width: "100%" }} placeholder="e.g. finance" value={selected.data.contains ?? ""}
                onChange={(e) => patchNode(selected.id, { contains: e.target.value })} />
            </>
          )}
          {selected.type === "notify" && (
            <>
              <label className="faint" style={{ fontSize: 11, display: "block", margin: "12px 0 4px" }}>Message</label>
              <textarea className="input sm" rows={3} style={{ width: "100%", resize: "vertical" }}
                value={selected.data.message ?? ""} onChange={(e) => patchNode(selected.id, { message: e.target.value })} />
              <p className="faint" style={{ fontSize: 10.5, lineHeight: 1.5 }}>Broadcast to the live activity feed (Agents app) via WebSocket.</p>
            </>
          )}
          <p className="faint" style={{ fontSize: 10.5, lineHeight: 1.55, marginTop: 14 }}>
            Tip: click a node's <b>right port</b>, then click another node to connect them.
          </p>
        </aside>
      )}
    </div>
  );
}
