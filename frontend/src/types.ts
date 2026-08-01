export type AppId =
  | "chat"
  | "knowledge"
  | "agents"
  | "graph"
  | "automations"
  | "traces"
  | "search"
  | "tasks"
  | "sql"
  | "analytics"
  | "dashboards"
  | "studio"
  | "connectors"
  | "meeting"
  | "video"
  | "code"
  | "admin"
  | "terminal"
  | "settings";

// ── Code app ──────────────────────────────────────────────────────────
export interface CodeProject {
  id: string;
  name: string;
  description: string;
  language: string;
  owner_id: string;
  files: number;
  created_at: string;
  updated_at: string;
}

export interface CodeFile {
  id: string;
  project_id: string;
  path: string;
  language: string;
  size_bytes: number;
  updated_by: string | null;
  updated_at: string;
  content?: string;
}

export interface FileVersionInfo {
  id: string;
  author_name: string;
  note: string;
  size: number;
  created_at: string;
}

export interface CollabPeer {
  user_id: string;
  name: string;
  hue: number;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Win {
  id: AppId;
  rect: Rect;
  z: number;
  minimized: boolean;
  maximized: boolean;
  prevRect?: Rect;
}

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "hr" | "manager" | "employee";
  avatar_hue: number;
}

export interface Doc {
  id: string;
  title: string;
  filename: string;
  doc_type: string;
  status: "indexed" | "processing" | "queued" | "failed";
  chunk_count: number;
  size_bytes: number;
  created_at: string;
  owner: string;
  tags: string[];
}

export interface AgentMeta {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  status: "idle" | "active";
  runs: number;
  avg_ms: number;
  hue: number;
}

export interface Citation {
  doc_id: string;
  title: string;
  section: string;
  score: number;
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent?: string;
  plan?: string[];
  citations?: Citation[];
  confidence?: number;
  streaming?: boolean;
}

export interface FeedEvent {
  id: number;
  time: string;
  agent: string;
  text: string;
  kind: "run" | "index" | "auth" | "system";
}

/* ── realtime ── */
export interface PresenceUser {
  id: string;
  name: string;
  hue: number;
  role: string;
}

/* ── knowledge graph ── */
export interface GraphNode {
  id: string;
  name: string;
  type: string; // person | org | money | date | acronym | concept | term
  mentions: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

/* ── workflows ── */
export type WfNodeType = "trigger" | "agent" | "condition" | "approve" | "notify";

export interface WfNode {
  id: string;
  type: WfNodeType;
  x: number;
  y: number;
  data: { label?: string; agent?: string; prompt?: string; contains?: string; message?: string; every?: string };
}

export interface WfEdge {
  from: string;
  to: string;
}

export interface WorkflowDef {
  id: string;
  name: string;
  description: string;
  trigger: "manual" | "upload" | "schedule";
  nodes: WfNode[];
  edges: WfEdge[];
  enabled: boolean;
  run_count: number;
  last_run_at: string | null;
}

export interface WfRunLogEntry {
  node: string;
  type: string;
  label: string;
  status: "ok" | "error";
  ms: number;
  output: string;
}

export interface WorkflowRunInfo {
  id: string;
  status: "running" | "ok" | "error" | "awaiting_approval";
  trigger: string;
  input: string;
  output: string;
  log: WfRunLogEntry[];
  duration_ms: number;
  created_at: string;
}

/* ── traces ── */
export interface TraceSpan {
  name: string;
  kind: "agent" | "llm" | "retrieval" | "graph" | "node" | "step";
  offset_ms: number;
  duration_ms: number;
  status: "ok" | "error";
  attrs: Record<string, string | number | boolean>;
}

export interface TraceInfo {
  id: string;
  name: string;
  kind: "chat" | "workflow";
  user: string;
  started_at: string;
  duration_ms: number;
  status: "ok" | "error";
  span_count?: number;
  spans?: TraceSpan[];
}

// ── Version control ───────────────────────────────────────────────────
export interface GitCommit {
  id: string;
  short: string;
  branch: string;
  message: string;
  author_name: string;
  parent_id: string | null;
  file_count: number;
  created_at: string;
}

export interface GitStatus {
  branch: string;
  head: string | null;
  added: string[];
  modified: string[];
  removed: string[];
  clean: boolean;
}

export interface GitDiffFile {
  path: string;
  change: "added" | "modified" | "removed";
  patch: string;
  additions?: number;
  deletions?: number;
}

export interface GitBranch {
  name: string;
  commits: number;
  updated_at: string | null;
}
