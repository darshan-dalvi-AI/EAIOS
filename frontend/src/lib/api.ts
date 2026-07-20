/* API client with graceful demo fallback.
   Live mode: requests hit the FastAPI backend (vite proxy → :8000).
   Demo mode: identical shapes served from mock.ts with realistic latency. */
import { useOS } from "../store";
import type { Citation, GraphEdge, GraphNode, SessionUser, TraceInfo, WorkflowDef, WorkflowRunInfo } from "../types";
import { DB_SCHEMA, DOCS, MOCK_GRAPH, MOCK_TRACES, MOCK_USERS, MOCK_WORKFLOWS, mockAnalyze, mockChart, mockChat, mockMinutes, mockRunWorkflow, mockSQL } from "./mock";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/* ── mid-session resilience ─────────────────────────────────────────
   If the backend process dies while the app is open (closed terminal,
   crash, redeploy), fetch fails at the NETWORK level. Instead of letting
   windows crash, we demote to demo mode (mock data keeps every app
   usable) and poll /api/health in the background to restore live mode
   the moment the backend returns. */
let recoveryTimer: number | null = null;

function notifyFeed(text: string) {
  useOS.getState().pushFeed({ agent: "system", text, kind: "system" });
}

function startRecoveryLoop() {
  if (recoveryTimer != null) return;
  recoveryTimer = window.setInterval(async () => {
    if (!(await ping())) return; // still down — keep waiting
    const stop = () => { if (recoveryTimer != null) { window.clearInterval(recoveryTimer); recoveryTimer = null; } };
    const { token } = useOS.getState();
    if (!token) { stop(); return; }
    try {
      const me = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
      if (me.ok) {
        useOS.getState().setLive(true);
        notifyFeed("Backend is back — live mode restored.");
      } else {
        // backend restarted with a fresh database → old session is gone
        notifyFeed("Backend is back, but your session expired (database was reset). Log out and back in for live mode.");
      }
      stop();
    } catch {
      /* went down again mid-check — keep polling */
    }
  }, 15000);
}

export function demoteToDemo(): void {
  const os = useOS.getState();
  if (!os.live) return;
  os.setLive(false);
  notifyFeed("Backend unreachable — switched to demo mode (mock data). Watching for it to come back…");
  startRecoveryLoop();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { token } = useOS.getState();
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch (err) {
    if ((err as DOMException)?.name === "AbortError") throw err;
    demoteToDemo(); // network-level failure: backend process is gone
    throw new Error("Backend unreachable — switched to demo mode. Try that again.");
  }
  if (!res.ok) {
    // FastAPI errors arrive as {"detail": "..."} — surface the human message, never raw JSON
    const raw = (await res.text().catch(() => "")) || "";
    let msg = raw;
    try {
      const j = JSON.parse(raw) as { detail?: unknown };
      if (j && j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* plain-text body */ }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function ping(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);
    const res = await fetch("/api/health", { signal: controller.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

export async function apiLogin(email: string, password: string): Promise<{ user: SessionUser; token: string | null; live: boolean }> {
  if (useOS.getState().live) {
    try {
      const data = await request<{ token: { access_token: string }; user: SessionUser }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      return { user: data.user, token: data.token.access_token, live: true };
    } catch (err) {
      // fall through to demo credentials so the UI is never a dead end
      const demo = MOCK_USERS.find((u) => u.email === email && u.password === password);
      if (!demo) throw err;
    }
  }
  await delay(600);
  const demo = MOCK_USERS.find((u) => u.email === email && u.password === password);
  if (!demo) throw new Error("Invalid credentials");
  const { password: _pw, ...user } = demo;
  return { user, token: null, live: false };
}

export interface ChatResult {
  agent: string;
  plan: string[];
  answer: string;
  citations: Citation[];
  confidence: number;
}

export async function apiChat(message: string, agent?: string): Promise<ChatResult> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try {
      const data = await request<{
        message: { content: string; agent: string; confidence: number };
        plan: string[];
        retrieved: Citation[];
      }>("/chat", { method: "POST", body: JSON.stringify({ message, agent: agent || null }) });
      return {
        agent: data.message.agent,
        plan: data.plan,
        answer: data.message.content,
        citations: data.retrieved,
        confidence: data.message.confidence,
      };
    } catch (err) {
      if (useOS.getState().live) throw err; // real API error — surface it
      /* backend died mid-session → demoted: answer from demo data instead */
    }
  }
  await delay(700 + Math.random() * 800);
  const reply = mockChat(message);
  return agent && agent !== "auto" ? { ...reply, agent, plan: [agent] } : reply;
}

/* ── streaming chat (SSE) ── */
export interface StreamMeta {
  conversation_id: string;
  agent: string;
  plan: string[];
  citations: Citation[];
  confidence: number;
}

async function streamMock(
  message: string,
  agent: string | undefined,
  handlers: { onMeta: (m: StreamMeta) => void; onDelta: (text: string) => void },
  signal?: AbortSignal,
): Promise<void> {
  await delay(450 + Math.random() * 500);
  const r = mockChat(message);
  const routed = agent && agent !== "auto" ? { ...r, agent, plan: [agent] } : r;
  handlers.onMeta({ conversation_id: "demo", agent: routed.agent, plan: routed.plan, citations: routed.citations, confidence: routed.confidence });
  const text = routed.answer;
  const step = Math.max(4, Math.floor(text.length / 110));
  for (let i = 0; i < text.length; i += step) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    handlers.onDelta(text.slice(i, i + step));
    await delay(13);
  }
}

export async function apiChatStream(
  message: string,
  agent: string | undefined,
  handlers: { onMeta: (m: StreamMeta) => void; onDelta: (text: string) => void },
  signal?: AbortSignal,
): Promise<void> {
  const { live, token } = useOS.getState();

  // demo mode: identical streaming behavior over mock data
  if (!(live && token)) return streamMock(message, agent, handlers, signal);

  let res: Response;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message, agent: agent || null }),
      signal,
    });
  } catch (err) {
    if ((err as DOMException)?.name === "AbortError") throw err;
    // backend process is gone → demote and answer this message from demo data
    demoteToDemo();
    return streamMock(message, agent, handlers, signal);
  }
  if (!res.ok || !res.body) throw new Error((await res.text().catch(() => "")) || `HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let done: boolean, value: Uint8Array | undefined;
    try {
      ({ done, value } = await reader.read());
    } catch (err) {
      if ((err as DOMException)?.name === "AbortError") throw err;
      // connection dropped mid-stream (backend closed while answering)
      demoteToDemo();
      handlers.onDelta("\n\n_Connection to the backend was lost mid-answer — EAIOS switched to demo mode._");
      return;
    }
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + 2);
      if (!raw.startsWith("data:")) continue;
      try {
        const ev = JSON.parse(raw.slice(5));
        if (ev.type === "meta") handlers.onMeta(ev);
        else if (ev.type === "delta") handlers.onDelta(ev.text);
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}

/* ── knowledge graph ── */
export async function apiGraph(q = ""): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const { live, token } = useOS.getState();
  if (live && token) return request(`/graph?q=${encodeURIComponent(q)}&limit=80`);
  await delay(350);
  if (!q) return MOCK_GRAPH;
  const ql = q.toLowerCase();
  const nodes = MOCK_GRAPH.nodes.filter((n) => n.name.toLowerCase().includes(ql));
  const ids = new Set(nodes.map((n) => n.id));
  return { nodes, edges: MOCK_GRAPH.edges.filter((e) => ids.has(e.source) && ids.has(e.target)) };
}

/* ── SQL assistant (live NL→SQL + database explorer) ── */
export interface SQLResult {
  sql: string;
  explanation: string;
  warning?: string;
  columns: string[];
  rows: (string | number)[][];
}

export interface SchemaTable {
  table: string;
  rows: number;
  columns: string[];
  source?: string; // set for structured tables extracted from uploaded documents
}

export async function apiSql(question: string): Promise<SQLResult> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try {
      return await request<SQLResult>("/agents/sql", { method: "POST", body: JSON.stringify({ question }) });
    } catch {
      /* fall through to demo shape */
    }
  }
  await delay(650);
  return mockSQL(question);
}

export async function apiSchema(): Promise<SchemaTable[]> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try {
      return await request<SchemaTable[]>("/agents/sql/schema");
    } catch {
      /* fall through */
    }
  }
  await delay(200);
  return DB_SCHEMA;
}

/* ── workflows ── */
type WorkflowWire = Omit<WorkflowDef, "nodes" | "edges"> & { nodes: string; edges: string };

const parseWf = (w: WorkflowWire): WorkflowDef => ({
  ...w,
  nodes: JSON.parse(w.nodes || "[]"),
  edges: JSON.parse(w.edges || "[]"),
});

let demoWorkflows: WorkflowDef[] | null = null;
const demoWfs = () => (demoWorkflows ??= structuredClone(MOCK_WORKFLOWS));

export async function apiWorkflows(): Promise<WorkflowDef[]> {
  const { live, token } = useOS.getState();
  if (live && token) return (await request<WorkflowWire[]>("/workflows")).map(parseWf);
  await delay(300);
  return demoWfs();
}

export async function apiSaveWorkflow(wf: WorkflowDef): Promise<WorkflowDef> {
  const { live, token } = useOS.getState();
  const body = JSON.stringify({
    name: wf.name, description: wf.description, trigger: wf.trigger,
    nodes: wf.nodes, edges: wf.edges, enabled: wf.enabled,
  });
  if (live && token) {
    const isNew = wf.id.startsWith("new-");
    const data = await request<WorkflowWire>(isNew ? "/workflows" : `/workflows/${wf.id}`, {
      method: isNew ? "POST" : "PUT",
      body,
    });
    return parseWf(data);
  }
  await delay(250);
  const list = demoWfs();
  const saved = { ...wf, id: wf.id.startsWith("new-") ? `wf-${Date.now()}` : wf.id };
  const i = list.findIndex((w) => w.id === wf.id);
  if (i >= 0) list[i] = saved;
  else list.unshift(saved);
  return saved;
}

export async function apiDeleteWorkflow(id: string): Promise<void> {
  const { live, token } = useOS.getState();
  if (live && token) {
    await request(`/workflows/${id}`, { method: "DELETE" });
    return;
  }
  await delay(200);
  demoWorkflows = demoWfs().filter((w) => w.id !== id);
}

export async function apiRunWorkflow(id: string, input: string): Promise<WorkflowRunInfo> {
  const { live, token } = useOS.getState();
  if (live && token) {
    const data = await request<Omit<WorkflowRunInfo, "log"> & { log: string }>(`/workflows/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ input }),
    });
    return { ...data, log: JSON.parse(data.log || "[]") };
  }
  await delay(500);
  const wf = demoWfs().find((w) => w.id === id);
  if (!wf) throw new Error("Workflow not found");
  return mockRunWorkflow(wf, input);
}

/* ── traces ── */
export async function apiTraces(): Promise<TraceInfo[]> {
  const { live, token } = useOS.getState();
  if (live && token) return request("/traces");
  await delay(300);
  return MOCK_TRACES.map(({ spans, ...t }) => ({ ...t, span_count: spans?.length ?? 0 }));
}

export async function apiTrace(id: string): Promise<TraceInfo> {
  const { live, token } = useOS.getState();
  if (live && token) return request(`/traces/${id}`);
  await delay(200);
  const t = MOCK_TRACES.find((x) => x.id === id);
  if (!t) throw new Error("Trace not found");
  return t;
}

/* ── admin: AI model config + hot-swap ── */
export interface ModelConfig {
  active_provider: string;
  active_model: string | null;
  temperature: number;
  router_mode: string;
  openai_base_url: string;
  openai_key_set: boolean;
  vector_backend: string;
}

const DEMO_CONFIG: ModelConfig = {
  active_provider: "mock", active_model: null, temperature: 0.3, router_mode: "auto",
  openai_base_url: "https://openrouter.ai/api/v1", openai_key_set: false, vector_backend: "in-memory",
};
let demoConfig: ModelConfig | null = null;

export async function apiModelConfig(): Promise<ModelConfig> {
  const { live, token } = useOS.getState();
  if (live && token) return request("/admin/config");
  await delay(200);
  return demoConfig ?? DEMO_CONFIG;
}

export async function apiSetModel(patch: {
  model?: string; base_url?: string; provider?: string; temperature?: number;
}): Promise<{ active_provider: string; active_model: string | null; temperature: number }> {
  const { live, token } = useOS.getState();
  if (live && token) return request("/admin/model", { method: "POST", body: JSON.stringify(patch) });
  await delay(300);
  const base = demoConfig ?? DEMO_CONFIG;
  demoConfig = {
    ...base,
    active_provider: patch.base_url?.includes("openrouter") ? "openrouter" : (patch.provider ?? base.active_provider),
    active_model: patch.model ?? base.active_model,
    temperature: patch.temperature ?? base.temperature,
    openai_base_url: patch.base_url ?? base.openai_base_url,
  };
  return { active_provider: demoConfig.active_provider, active_model: demoConfig.active_model, temperature: demoConfig.temperature };
}

export async function apiApproveRun(runId: string, approved: boolean): Promise<WorkflowRunInfo> {
  const { live, token } = useOS.getState();
  if (live && token) {
    const data = await request<Omit<WorkflowRunInfo, "log"> & { log: string }>(
      `/workflows/runs/${runId}/approve`, { method: "POST", body: JSON.stringify({ approved }) });
    return { ...data, log: JSON.parse(data.log || "[]") };
  }
  await delay(300);
  throw new Error("Approvals require the live backend");
}

/* ── report exports (PDF / DOCX artifacts from any agent answer) ── */
export async function apiExportReport(title: string, content: string, format: "pdf" | "docx" | "md"): Promise<void> {
  const { live, token } = useOS.getState();
  if (live && token) {
    const res = await fetch("/api/reports/export", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ title, content, format }),
    });
    if (!res.ok) throw new Error((await res.text().catch(() => "")) || `HTTP ${res.status}`);
    const blob = await res.blob();
    const name = (res.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1])
      || `eaios-report.${format}`;
    triggerDownload(blob, name);
    return;
  }
  // demo mode: markdown download works entirely client-side
  triggerDownload(new Blob([content], { type: "text/markdown" }),
    `${title.replace(/[^a-z0-9]+/gi, "-").toLowerCase() || "eaios-report"}.md`);
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* ── AI meeting assistant ── */
export async function apiMeeting(transcript: string, title: string, saveToKnowledge: boolean):
  Promise<{ minutes: string; doc_id: string | null }> {
  const { live, token } = useOS.getState();
  if (live && token) {
    return request("/agents/meeting", {
      method: "POST",
      body: JSON.stringify({ transcript, title, save_to_knowledge: saveToKnowledge }),
    });
  }
  await delay(900);
  return { minutes: mockMinutes(transcript), doc_id: null };
}

/* ── model arena (admin) ── */
export interface CompareResult { model: string; ms: number; answer: string; error: string | null }

export async function apiCompare(prompt: string, models: [string, string]):
  Promise<{ prompt: string; results: CompareResult[] }> {
  const { live, token } = useOS.getState();
  if (live && token) {
    return request("/admin/compare", { method: "POST", body: JSON.stringify({ prompt, models }) });
  }
  await delay(1100);
  return {
    prompt,
    results: models.map((m, i) => ({
      model: m, ms: 640 + i * 420 + Math.floor(Math.random() * 200),
      answer: `[${m}] ${mockChat(prompt).answer}`, error: null,
    })),
  };
}

/* ── document analyzers ── */
export interface AnalyzeCard {
  doc_id: string; title: string; kind: string; verdict: string; score: number;
  highlights: { label: string; value: string; status: "good" | "warn" | "bad" }[];
  summary: string; engine: string;
}

export async function apiAnalyze(docId: string, kind: string, docTitle: string): Promise<AnalyzeCard> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try {
      return await request(`/documents/${docId}/analyze`, { method: "POST", body: JSON.stringify({ kind }) });
    } catch {
      /* doc not on the backend (demo row) → deterministic demo scorecard */
    }
  }
  await delay(800);
  return mockAnalyze(docId, kind, docTitle);
}

/* ── NL-to-BI dashboards ── */
export interface ChartSpec {
  question: string; sql: string; explanation?: string; warning?: string;
  type: "bar" | "line" | "pie" | "table"; x: string | null; series: string[];
  columns: string[]; rows: (string | number)[][]; data?: Record<string, string | number>[]; note?: string;
}
export interface SavedChartRow { id: string; question: string; sql: string; spec: ChartSpec; created_at: string }

export async function apiChart(question: string): Promise<ChartSpec> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try { return await request("/dashboards/chart", { method: "POST", body: JSON.stringify({ question }) }); }
    catch { /* fall through to demo */ }
  }
  await delay(650);
  return mockChart(question);
}
let demoPins: SavedChartRow[] | null = null;
export async function apiListCharts(): Promise<SavedChartRow[]> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/dashboards"); } catch { /* demo */ } }
  await delay(150);
  return (demoPins ??= []);
}
export async function apiPinChart(spec: ChartSpec): Promise<string> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try { return (await request<{ id: string }>("/dashboards", { method: "POST", body: JSON.stringify({ question: spec.question, sql: spec.sql, spec }) })).id; }
    catch { /* demo */ }
  }
  const id = `demo-${Date.now()}`;
  (demoPins ??= []).unshift({ id, question: spec.question, sql: spec.sql, spec, created_at: new Date().toISOString() });
  return id;
}
export async function apiUnpinChart(id: string): Promise<void> {
  const { live, token } = useOS.getState();
  if (live && token) { try { await request(`/dashboards/${id}`, { method: "DELETE" }); return; } catch { /* demo */ } }
  demoPins = (demoPins ?? []).filter((c) => c.id !== id);
}

/* ── Agent Studio ── */
export interface StudioAgent {
  id: string; slug: string; name: string; description: string;
  system_prompt: string; tools: string[]; hue: number; enabled: boolean; run_count: number;
}
export type StudioDraft = Omit<StudioAgent, "id" | "slug" | "run_count">;

let demoAgents: StudioAgent[] | null = null;
const seedDemoAgents = (): StudioAgent[] => (demoAgents ??= [
  { id: "demo-hr", slug: "studio_hr_helper", name: "HR Helper", description: "Answers HR & policy questions from the knowledge base",
    system_prompt: "You are a friendly HR assistant. Answer clearly and cite the relevant policy.", tools: ["rag"], hue: 150, enabled: true, run_count: 12 },
  { id: "demo-sales", slug: "studio_deal_coach", name: "Deal Coach", description: "Sales objection handling & pitch tips",
    system_prompt: "You are a sales coach. Give concise, actionable advice for the deal described.", tools: [], hue: 30, enabled: true, run_count: 5 },
]);

export async function apiStudioList(): Promise<StudioAgent[]> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/studio/agents"); } catch { /* demo */ } }
  await delay(200);
  return seedDemoAgents();
}
export async function apiStudioSave(draft: StudioDraft, id?: string): Promise<StudioAgent> {
  const { live, token } = useOS.getState();
  if (live && token) {
    try {
      return id
        ? await request(`/studio/agents/${id}`, { method: "PUT", body: JSON.stringify(draft) })
        : await request("/studio/agents", { method: "POST", body: JSON.stringify(draft) });
    } catch { /* demo */ }
  }
  await delay(250);
  const list = seedDemoAgents();
  if (id) {
    const i = list.findIndex((a) => a.id === id);
    if (i >= 0) list[i] = { ...list[i], ...draft };
    return list[i];
  }
  const created: StudioAgent = { ...draft, id: `demo-${Date.now()}`, slug: `studio_${draft.name.toLowerCase().replace(/[^a-z0-9]+/g, "_")}`, run_count: 0 };
  list.unshift(created);
  return created;
}
export async function apiStudioDelete(id: string): Promise<void> {
  const { live, token } = useOS.getState();
  if (live && token) { try { await request(`/studio/agents/${id}`, { method: "DELETE" }); return; } catch { /* demo */ } }
  demoAgents = (demoAgents ?? []).filter((a) => a.id !== id);
}
export async function apiStudioRun(id: string, input: string): Promise<{ answer: string; confidence: number }> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request(`/studio/agents/${id}/run`, { method: "POST", body: JSON.stringify({ input }) }); } catch { /* demo */ } }
  await delay(700);
  const a = seedDemoAgents().find((x) => x.id === id);
  return { answer: `**${a?.name ?? "Agent"}** (demo): ${mockChat(input).answer}`, confidence: 74 };
}

/* ── Connectors ── */
export interface ConnectorRow {
  id: string; provider: string; label: string; status: string; detail: string;
  synced_count: number; last_sync_at: string | null;
}
/* ── Tasks (kanban) ── */
export interface TaskRow { id: string; title: string; status: "todo" | "doing" | "done"; source: string; assignee_id: string | null; assignee: string | null; created_at: string }
let demoTasks: TaskRow[] | null = null;
const seedDemoTasks = (): TaskRow[] => (demoTasks ??= [
  { id: "dt1", title: "Update the security policy by Friday", status: "todo", source: "meeting", assignee_id: null, assignee: null, created_at: new Date().toISOString() },
  { id: "dt2", title: "Prepare the demo environment", status: "doing", source: "meeting", assignee_id: null, assignee: "Maya Iyer", created_at: new Date().toISOString() },
  { id: "dt3", title: "Review Q3 revenue report", status: "done", source: "manual", assignee_id: null, assignee: null, created_at: new Date().toISOString() },
]);
export async function apiTasks(): Promise<TaskRow[]> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/tasks"); } catch { /* demo */ } }
  await delay(150);
  return seedDemoTasks();
}
export async function apiTaskCreate(title: string): Promise<TaskRow> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/tasks", { method: "POST", body: JSON.stringify({ title }) }); } catch { /* demo */ } }
  const t: TaskRow = { id: `d-${Date.now()}`, title, status: "todo", source: "manual", assignee_id: null, assignee: null, created_at: new Date().toISOString() };
  seedDemoTasks().unshift(t);
  return t;
}
export async function apiTaskPatch(id: string, patch: Partial<Pick<TaskRow, "status" | "assignee_id" | "title">>): Promise<TaskRow> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(patch) }); } catch { /* demo */ } }
  const list = seedDemoTasks(); const i = list.findIndex((x) => x.id === id);
  if (i >= 0) list[i] = { ...list[i], ...patch } as TaskRow;
  return list[i];
}
export async function apiTaskDelete(id: string): Promise<void> {
  const { live, token } = useOS.getState();
  if (live && token) { try { await request(`/tasks/${id}`, { method: "DELETE" }); return; } catch { /* demo */ } }
  demoTasks = seedDemoTasks().filter((x) => x.id !== id);
}

/* ── Global search ── */
export interface SearchResults {
  query: string;
  documents: { id: string; title: string; doc_type: string; status: string }[];
  passages: { doc_id: string; title: string; section: string; text: string; score: number }[];
  entities: { id: string; name: string; type: string; mentions: number }[];
  tables: { name: string; source: string; rows: number }[];
  messages: { conversation: string; role: string; snippet: string; at: string }[];
}
export async function apiSearch(q: string): Promise<SearchResults> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request(`/search?q=${encodeURIComponent(q)}`); } catch { /* demo */ } }
  await delay(300);
  const ql = q.toLowerCase();
  const docs = DOCS.filter((d) => d.title.toLowerCase().includes(ql));
  return {
    query: q,
    documents: docs.slice(0, 6).map((d) => ({ id: d.id, title: d.title, doc_type: d.doc_type, status: d.status })),
    passages: docs.slice(0, 3).map((d) => ({ doc_id: d.id, title: d.title, section: "§1", text: `Demo passage matching “${q}” inside ${d.title}…`, score: 0.82 })),
    entities: ql.length > 2 ? [{ id: "e1", name: q[0].toUpperCase() + q.slice(1), type: "concept", mentions: 4 }] : [],
    tables: /sales|revenue|table/.test(ql) ? [{ name: "dt_regional_sales_1", source: "Regional Sales.csv", rows: 4 }] : [],
    messages: [],
  };
}

/* ── Compliance ── */
export async function apiExportMyData(): Promise<void> {
  const { live, token, user } = useOS.getState();
  let data: unknown;
  if (live && token) data = await request("/me/export");
  else { await delay(300); data = { user, note: "Demo-mode export — connect the backend for your real data." }; }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `eaios-export-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}
export async function apiDeleteMyData(): Promise<{ removed: Record<string, number> }> {
  const { live, token } = useOS.getState();
  if (live && token) return request("/me/data", { method: "DELETE" });
  await delay(300);
  return { removed: { conversations: 0 } };
}

/* ── Metering + RAG eval ── */
export interface AiUsage { window_days: number; note: string; by_user: { user: string; requests: number; tokens: number; est_cost: number }[]; by_model: { model: string; requests: number; tokens: number; est_cost: number }[] }
export async function apiAiUsage(): Promise<AiUsage> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/analytics/ai-usage"); } catch { /* demo */ } }
  await delay(200);
  return { window_days: 30, note: "demo data", by_user: [
    { user: "System Administrator", requests: 42, tokens: 61200, est_cost: 0.0122 },
    { user: "Maya Iyer", requests: 18, tokens: 24400, est_cost: 0.0049 },
    { user: "Dev Sharma", requests: 9, tokens: 8100, est_cost: 0.0016 },
  ], by_model: [{ model: "meta-llama/llama-3.3-70b-instruct", requests: 69, tokens: 93700, est_cost: 0.0187 }] };
}
export async function apiRagEval(): Promise<{ queries: number; hit_rate: number | null; mrr: number | null; note: string }> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/analytics/rag-eval"); } catch { /* demo */ } }
  await delay(250);
  return { queries: 6, hit_rate: 0.83, mrr: 0.78, note: "demo numbers — hit-rate@3 and MRR over the built-in eval set" };
}

export async function apiConnectorConfig(): Promise<{ google_client_id: string }> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/connectors/config"); } catch { /* demo */ } }
  return { google_client_id: "" };
}
let demoConnectors: ConnectorRow[] | null = null;
export async function apiConnectors(): Promise<ConnectorRow[]> {
  const { live, token } = useOS.getState();
  if (live && token) { try { return await request("/connectors"); } catch { /* demo */ } }
  await delay(150);
  return (demoConnectors ??= []);
}
export async function apiSyncConnector(provider: string, tokenStr = ""): Promise<ConnectorRow & { ingested: number }> {
  const { live, token } = useOS.getState();
  if (live && token) {
    return request("/connectors/sync", { method: "POST", body: JSON.stringify({ provider, token: tokenStr }) });
  }
  await delay(1100);
  if (provider !== "sample") throw new Error("Live backend required to connect real Google accounts.");
  const row: ConnectorRow & { ingested: number } = {
    id: "demo-sample", provider: "sample", label: "Sample Workspace", status: "connected",
    detail: "Ingested 5 item(s).", synced_count: 5, last_sync_at: new Date().toISOString(), ingested: 5,
  };
  demoConnectors = [row, ...(demoConnectors ?? []).filter((c) => c.provider !== "sample")];
  return row;
}
