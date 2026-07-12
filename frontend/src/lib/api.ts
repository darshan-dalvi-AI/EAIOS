/* API client with graceful demo fallback.
   Live mode: requests hit the FastAPI backend (vite proxy → :8000).
   Demo mode: identical shapes served from mock.ts with realistic latency. */
import { useOS } from "../store";
import type { Citation, GraphEdge, GraphNode, SessionUser, TraceInfo, WorkflowDef, WorkflowRunInfo } from "../types";
import { DB_SCHEMA, MOCK_GRAPH, MOCK_TRACES, MOCK_USERS, MOCK_WORKFLOWS, mockChat, mockRunWorkflow, mockSQL } from "./mock";

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
  if (!res.ok) throw new Error((await res.text().catch(() => "")) || `HTTP ${res.status}`);
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
