/* Demo-mode data layer — mirrors the backend's shapes so the OS is fully
   explorable with no server running. When the FastAPI backend is reachable,
   api.ts transparently switches to live data. */
import type {
  AgentMeta, Citation, Doc, FeedEvent, GraphEdge, GraphNode, SessionUser,
  TraceInfo, WfRunLogEntry, WorkflowDef, WorkflowRunInfo,
} from "../types";

export const MOCK_USERS: (SessionUser & { password: string })[] = [
  { id: "u1", email: "admin@eaios.dev", full_name: "System Administrator", role: "admin", avatar_hue: 265, password: "admin12345" },
  { id: "u2", email: "maya@eaios.dev", full_name: "Maya Iyer", role: "manager", avatar_hue: 180, password: "demo12345" },
  { id: "u3", email: "dev@eaios.dev", full_name: "Darshan Dalvi", role: "employee", avatar_hue: 210, password: "demo12345" },
];

export const DOCS: Doc[] = [
  { id: "d1", title: "HR Leave Policy", filename: "HR_Leave_Policy.pdf", doc_type: "pdf", status: "indexed", chunk_count: 18, size_bytes: 482_000, created_at: "2026-06-02", owner: "System Administrator", tags: ["hr", "policy"] },
  { id: "d2", title: "Q3 Financial Summary", filename: "Q3_Financial_Summary.xlsx", doc_type: "xlsx", status: "indexed", chunk_count: 31, size_bytes: 1_240_000, created_at: "2026-06-11", owner: "Maya Iyer", tags: ["finance", "quarterly"] },
  { id: "d3", title: "Atlas Product Manual", filename: "Atlas_Product_Manual.docx", doc_type: "docx", status: "indexed", chunk_count: 54, size_bytes: 2_310_000, created_at: "2026-06-15", owner: "System Administrator", tags: ["product", "docs"] },
  { id: "d4", title: "Security Incident SOP", filename: "Security_Incident_SOP.pdf", doc_type: "pdf", status: "indexed", chunk_count: 12, size_bytes: 356_000, created_at: "2026-06-18", owner: "System Administrator", tags: ["security", "sop"] },
  { id: "d5", title: "Vendor Contract — Nimbus Cloud", filename: "Nimbus_Contract_2026.pdf", doc_type: "pdf", status: "indexed", chunk_count: 44, size_bytes: 3_780_000, created_at: "2026-06-20", owner: "Maya Iyer", tags: ["legal", "contract"] },
  { id: "d6", title: "Sales Pipeline Q3", filename: "Sales_Pipeline_Q3.csv", doc_type: "csv", status: "indexed", chunk_count: 9, size_bytes: 210_000, created_at: "2026-06-24", owner: "Darshan Dalvi", tags: ["sales"] },
  { id: "d7", title: "Onboarding Deck v4", filename: "Onboarding_Deck_v4.pptx", doc_type: "pptx", status: "processing", chunk_count: 0, size_bytes: 5_920_000, created_at: "2026-07-02", owner: "Maya Iyer", tags: ["hr", "onboarding"] },
  { id: "d8", title: "Scanned Invoice #8841", filename: "invoice_8841.png", doc_type: "image", status: "indexed", chunk_count: 3, size_bytes: 890_000, created_at: "2026-07-01", owner: "Darshan Dalvi", tags: ["finance", "ocr"] },
  { id: "d9", title: "Engineering Handbook", filename: "Engineering_Handbook.md", doc_type: "txt", status: "indexed", chunk_count: 27, size_bytes: 145_000, created_at: "2026-06-28", owner: "System Administrator", tags: ["engineering"] },
  { id: "d10", title: "Board Meeting Notes — June", filename: "Board_Notes_June.docx", doc_type: "docx", status: "failed", chunk_count: 0, size_bytes: 88_000, created_at: "2026-07-02", owner: "Maya Iyer", tags: ["exec"] },
];

export const AGENTS: AgentMeta[] = [
  { id: "planning", name: "Planning Agent", description: "Decomposes complex requests and coordinates the other agents.", capabilities: ["Task decomposition", "Agent routing", "Multi-step chains"], status: "active", runs: 1284, avg_ms: 96, hue: 265 },
  { id: "document", name: "Document Agent", description: "RAG answers over the enterprise knowledge base with citations.", capabilities: ["Hybrid retrieval", "Citations", "Summaries"], status: "active", runs: 3411, avg_ms: 840, hue: 190 },
  { id: "sql", name: "SQL Agent", description: "Natural language to safe, read-only SQL with result tables.", capabilities: ["NL → SQL", "Guardrails", "Schema explain"], status: "idle", runs: 762, avg_ms: 310, hue: 150 },
  { id: "research", name: "Research Agent", description: "Live web search with source citations and fact checks.", capabilities: ["Web search", "News", "Citations"], status: "idle", runs: 429, avg_ms: 1720, hue: 30 },
  { id: "email", name: "Email Agent", description: "Drafts professional emails and replies in your voice.", capabilities: ["Drafting", "Replies", "Tone control"], status: "idle", runs: 233, avg_ms: 650, hue: 330 },
  { id: "report", name: "Report Agent", description: "Structured reports and executive summaries from sources.", capabilities: ["Exec summaries", "Markdown reports"], status: "idle", runs: 187, avg_ms: 1980, hue: 210 },
  { id: "analytics", name: "Analytics Agent", description: "Computes usage metrics and narrates business insights.", capabilities: ["KPIs", "Trends", "Insights"], status: "active", runs: 356, avg_ms: 140, hue: 45 },
  { id: "memory", name: "Memory Agent", description: "Long-term user memory: preferences, facts, project context.", capabilities: ["Store", "Recall", "Personalize"], status: "idle", runs: 149, avg_ms: 55, hue: 285 },
  { id: "coding", name: "Coding Agent", description: "Explains, generates, reviews, and debugs code; grounded in engineering docs.", capabilities: ["Code generation", "Review & debug", "Optimization"], status: "idle", runs: 512, avg_ms: 1240, hue: 15 },
];

const FEED_TEMPLATES: [string, string, FeedEvent["kind"]][] = [
  ["document", "Answered “annual leave carry-forward” with 3 citations (conf. 91%)", "run"],
  ["planning", "Decomposed request into 2 subtasks → document, email", "run"],
  ["sql", "Executed SELECT doc_type, COUNT(*) … (6 rows, 12 ms)", "run"],
  ["system", "Indexed Onboarding_Deck_v4.pptx → 38 chunks", "index"],
  ["analytics", "Generated weekly adoption digest for #leadership", "run"],
  ["memory", "Stored preference: “summaries under 200 words”", "run"],
  ["system", "maya@eaios.dev signed in from 10.0.4.12", "auth"],
  ["research", "Fetched 4 sources for “EU AI Act enforcement”", "run"],
  ["report", "Built exec summary “Q3 revenue drivers” (1,240 words)", "run"],
  ["document", "Summarized Nimbus contract §7 termination clauses", "run"],
];

let feedCounter = 0;
export function nextFeedEvent(): FeedEvent {
  const [agent, text, kind] = FEED_TEMPLATES[feedCounter % FEED_TEMPLATES.length];
  feedCounter += 1;
  return { id: feedCounter, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }), agent, text, kind };
}

export const MESSAGES_DAILY = Array.from({ length: 14 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() - (13 - i));
  return { date: d.toLocaleDateString([], { month: "short", day: "numeric" }), count: [42, 51, 38, 64, 71, 59, 24, 18, 83, 92, 76, 88, 104, 97][i] };
});

export const DOCS_BY_TYPE = [
  { type: "pdf", count: 128 }, { type: "docx", count: 84 }, { type: "xlsx", count: 61 },
  { type: "pptx", count: 37 }, { type: "csv", count: 29 }, { type: "image", count: 22 },
];

export const AGENT_USAGE = AGENTS.map((a) => ({ name: a.name.replace(" Agent", ""), value: a.runs }));

export const AUDIT_ROWS = [
  { time: "09:41:22", user: "admin@eaios.dev", action: "model.config", detail: "LLM provider → ollama/llama3.1" },
  { time: "09:38:10", user: "maya@eaios.dev", action: "document.upload", detail: "Onboarding_Deck_v4.pptx (5.9 MB)" },
  { time: "09:31:47", user: "dev@eaios.dev", action: "auth.login", detail: "ip=10.0.4.31" },
  { time: "09:22:05", user: "maya@eaios.dev", action: "chat.query", detail: "agent=document conf=91%" },
  { time: "09:15:33", user: "admin@eaios.dev", action: "user.update", detail: "dev@eaios.dev role → employee" },
  { time: "08:58:19", user: "system", action: "index.complete", detail: "Sales_Pipeline_Q3.csv → 9 chunks" },
  { time: "08:44:02", user: "maya@eaios.dev", action: "report.generate", detail: "Q3 revenue drivers" },
  { time: "08:31:56", user: "admin@eaios.dev", action: "auth.login", detail: "ip=10.0.1.2" },
];

export const DB_SCHEMA: { table: string; rows: number; columns: string[] }[] = [
  { table: "users", rows: 3, columns: ["id", "email", "full_name", "role", "is_active", "created_at", "last_login"] },
  { table: "documents", rows: 10, columns: ["id", "filename", "title", "doc_type", "status", "chunk_count", "owner_id", "created_at"] },
  { table: "chunks", rows: 198, columns: ["id", "document_id", "ord", "text", "section", "page"] },
  { table: "conversations", rows: 24, columns: ["id", "user_id", "title", "created_at", "updated_at"] },
  { table: "messages", rows: 312, columns: ["id", "conversation_id", "role", "content", "agent", "confidence", "created_at"] },
  { table: "agent_runs", rows: 6811, columns: ["id", "agent", "user_id", "status", "duration_ms", "created_at"] },
  { table: "audit_logs", rows: 1490, columns: ["id", "user_id", "action", "detail", "ip", "created_at"] },
];

export function mockSQL(question: string): { sql: string; explanation: string; columns: string[]; rows: (string | number)[][] } {
  const q = question.toLowerCase();
  if (q.includes("type"))
    return {
      sql: "SELECT doc_type, COUNT(*) AS total\nFROM documents\nGROUP BY doc_type\nORDER BY total DESC",
      explanation: "Grouped document counts by file type. Read-only guardrails enforced (SELECT-only, LIMIT 50).",
      columns: ["doc_type", "total"],
      rows: [["pdf", 3], ["docx", 2], ["xlsx", 1], ["csv", 1], ["pptx", 1], ["image", 1], ["txt", 1]],
    };
  if (q.includes("agent"))
    return {
      sql: "SELECT agent, COUNT(*) AS runs, ROUND(AVG(duration_ms)) AS avg_ms\nFROM agent_runs\nGROUP BY agent\nORDER BY runs DESC",
      explanation: "Agent workload with mean latency, most active first.",
      columns: ["agent", "runs", "avg_ms"],
      rows: [["document", 3411, 840], ["planning", 1284, 96], ["sql", 762, 310], ["research", 429, 1720], ["analytics", 356, 140]],
    };
  if (q.includes("user") && (q.includes("how many") || q.includes("count")))
    return { sql: "SELECT COUNT(*) AS total FROM users", explanation: "Simple aggregate over the users table.", columns: ["total"], rows: [[3]] };
  if (q.includes("recent") || q.includes("latest"))
    return {
      sql: "SELECT title, status, chunk_count, created_at\nFROM documents\nORDER BY created_at DESC\nLIMIT 5",
      explanation: "Five most recently uploaded documents.",
      columns: ["title", "status", "chunk_count", "created_at"],
      rows: DOCS.slice(6, 10).reverse().map((d) => [d.title, d.status, d.chunk_count, d.created_at]),
    };
  return {
    sql: "SELECT role, COUNT(*) AS total\nFROM users\nGROUP BY role",
    explanation: "Defaulted to a role breakdown — try “documents by type” or “agent runs”.",
    columns: ["role", "total"],
    rows: [["admin", 1], ["manager", 1], ["employee", 1]],
  };
}

export const MEMORIES = [
  { id: "m1", kind: "preference", content: "Prefers executive summaries under 200 words", created_at: "2026-06-14" },
  { id: "m2", kind: "project", content: "Leading the Atlas HA deployment project (Q4)", created_at: "2026-06-20" },
  { id: "m3", kind: "fact", content: "Fiscal year starts in April", created_at: "2026-06-27" },
];

/* ── Canned RAG exchanges (mirror backend mock LLM behavior) ── */
const cite = (id: string, title: string, section: string, score: number): Citation => ({ doc_id: id, title, section, score });

export function mockChat(text: string): { agent: string; plan: string[]; answer: string; citations: Citation[]; confidence: number } {
  const q = text.toLowerCase();
  if (/remember|know about me/.test(q))
    return { agent: "memory", plan: ["memory"], answer: "Saved to long-term memory. I'll use this to personalize future answers — you can review everything I know in the Memory section of Settings.", citations: [], confidence: 95 };
  if (/\b(sql|database|table|how many (users|documents|messages))\b/.test(q)) {
    const r = mockSQL(text);
    return { agent: "sql", plan: ["planning", "sql"], answer: `I generated and executed this query:\n\n${r.sql}\n\n${r.explanation}`, citations: [], confidence: 85 };
  }
  if (/email|draft|reply/.test(q))
    return { agent: "email", plan: ["planning", "email"], answer: "Subject: Following up on the Atlas deployment timeline\n\nHi Priya,\n\nI hope you're doing well. I wanted to follow up on the Atlas HA rollout — per the admin manual, the 3-node configuration requires load-balancer provisioning before the cutover window. Could we confirm infra sign-off by Friday?\n\nBest regards,\nMaya", citations: [cite("d3", "Atlas Product Manual", "Deployment", 0.81)], confidence: 82 };
  if (/report|executive summary|briefing/.test(q))
    return { agent: "report", plan: ["planning", "document", "report"], answer: "# Report: Q3 Performance\n\n## Executive Summary\nQ3 revenue reached $48.2M, up 14% YoY, driven by Enterprise growth of 22% ($29.5M). Gross margin improved to 71% on $1.8M of cloud savings.\n\n## Key Findings\nEnterprise momentum offset flat SMB revenue ($12.1M). R&D remains the largest opex line at $11.2M (41%).\n\n## Recommendations\nProtect Enterprise pipeline coverage in EMEA where sales cycles are elongating; currency headwinds estimated at 1.5% of revenue.", citations: [cite("d2", "Q3 Financial Summary", "Revenue", 0.93), cite("d2", "Q3 Financial Summary", "Outlook", 0.77)], confidence: 88 };
  if (/\b(code|coding|function|script|debug|refactor|regex|python|javascript|typescript|unit test|algorithm)\b/.test(q))
    return { agent: "coding", plan: ["planning", "coding"], answer: "Here's a clean implementation with input validation and a docstring:\n\n```python\ndef restore_backup(timestamp: str, *, dry_run: bool = False) -> int:\n    \"\"\"Restore the Atlas database to a point in time.\n\n    Args:\n        timestamp: ISO-8601 restore point (within the 7-day PITR window).\n        dry_run: validate the restore plan without applying it.\n    Returns:\n        Exit code from atlasctl (0 = success).\n    \"\"\"\n    from datetime import datetime\n    datetime.fromisoformat(timestamp)  # raises ValueError if malformed\n    cmd = [\"atlasctl\", \"restore\", \"--timestamp\", timestamp]\n    if dry_run:\n        cmd.append(\"--dry-run\")\n    import subprocess\n    return subprocess.run(cmd, check=False).returncode\n```\n\nKey points: the ISO check fails fast before touching the cluster [1], PITR is limited to 7 days per the product manual [1], and `--dry-run` lets you validate against a live cluster safely.", citations: [cite("d3", "Atlas Product Manual", "Backup & Recovery", 0.87)], confidence: 85 };
  if (/leave|vacation|holiday/.test(q))
    return { agent: "document", plan: ["document"], answer: "Based on the indexed enterprise documents: All full-time employees accrue 24 days of paid annual leave per calendar year, credited monthly at 2 days per month [1]. Unused leave up to 10 days may be carried forward to the next year; the remainder lapses on 31 December [1]. Sick leave is separate: 12 paid days annually, with a medical certificate required beyond 2 consecutive days [2].", citations: [cite("d1", "HR Leave Policy", "Annual Leave", 0.94), cite("d1", "HR Leave Policy", "Sick Leave", 0.71)], confidence: 91 };
  if (/revenue|financ|q3|margin/.test(q))
    return { agent: "document", plan: ["document"], answer: "Q3 revenue reached $48.2M, up 14% year-over-year, driven primarily by the Enterprise segment which grew 22% to $29.5M [1]. Gross margin improved to 71% from 68% last quarter due to cloud cost optimization that saved $1.8M [2]. Q4 guidance is $52–54M with EMEA sales-cycle risk flagged [3].", citations: [cite("d2", "Q3 Financial Summary", "Revenue", 0.95), cite("d2", "Q3 Financial Summary", "Costs & Margin", 0.84), cite("d2", "Q3 Financial Summary", "Outlook", 0.69)], confidence: 92 };
  if (/backup|restore|atlas|recovery/.test(q))
    return { agent: "document", plan: ["document"], answer: "Automated backups run nightly at 02:00 UTC with 30-day retention [1]. Point-in-time recovery is supported up to 7 days. To restore, run `atlasctl restore --timestamp <ISO8601>` from any admin node [1]. Note that high-availability mode requires 3 nodes behind a load balancer [2].", citations: [cite("d3", "Atlas Product Manual", "Backup & Recovery", 0.92), cite("d3", "Atlas Product Manual", "Deployment", 0.66)], confidence: 89 };
  if (/incident|breach|sev|security/.test(q))
    return { agent: "document", plan: ["document"], answer: "For a SEV-1 (active breach or data exfiltration): respond within 15 minutes and notify the CISO immediately [1]. The response sequence is Contain → Assess → Eradicate → Recover → Review, with a blameless postmortem due within 5 business days [1]. Legal must be looped in for any incident involving personal data [2].", citations: [cite("d4", "Security Incident SOP", "Severity Levels", 0.93), cite("d4", "Security Incident SOP", "Contacts", 0.64)], confidence: 90 };
  if (/search|news|latest|web/.test(q))
    return { agent: "research", plan: ["planning", "research"], answer: "From live web sources: enterprise RAG adoption continues to accelerate, with hybrid retrieval (dense + lexical fusion) now the default architecture in most production deployments. Multimodal document understanding — tables, charts, scanned pages — is the differentiator enterprises cite most. • Vector databases are consolidating around HNSW indexes • Agent orchestration frameworks are converging on graph-based state machines.", citations: [cite("web", "DuckDuckGo", "https://duckduckgo.com", 0.8)], confidence: 74 };
  return { agent: "document", plan: ["document"], answer: `I searched the knowledge base for “${text.slice(0, 80)}” but didn't find a confident match. Try asking about the leave policy, Q3 financials, Atlas backups, or the security SOP — or upload a document in the Knowledge app and ask again.`, citations: [], confidence: 40 };
}

export function fmtBytes(n: number): string {
  if (n > 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n > 1_000) return `${Math.round(n / 1_000)} KB`;
  return `${n} B`;
}

/* ── knowledge graph (extracted from the mock corpus) ── */
const gn = (id: string, name: string, type: string, mentions: number): GraphNode => ({ id, name, type, mentions });
const ge = (source: string, target: string, weight: number): GraphEdge => ({ source, target, weight });

export const MOCK_GRAPH: { nodes: GraphNode[]; edges: GraphEdge[] } = {
  nodes: [
    gn("e1", "Atlas", "concept", 42), gn("e2", "Annual Leave", "concept", 31), gn("e3", "Q3 Revenue", "concept", 28),
    gn("e4", "Maya Iyer", "person", 24), gn("e5", "Nimbus Cloud", "org", 22), gn("e6", "Enterprise Segment", "concept", 19),
    gn("e7", "CISO", "acronym", 17), gn("e8", "Load Balancer", "concept", 15), gn("e9", "SEV-1", "acronym", 14),
    gn("e10", "$48.2M", "money", 12), gn("e11", "Sick Leave", "concept", 12), gn("e12", "December", "date", 11),
    gn("e13", "Priya Sharma", "person", 10), gn("e14", "Gross Margin", "concept", 10), gn("e15", "EMEA", "acronym", 9),
    gn("e16", "Point-in-Time Recovery", "concept", 8), gn("e17", "Blameless Postmortem", "concept", 7),
    gn("e18", "Termination Clause", "concept", 7), gn("e19", "HR Department", "org", 6), gn("e20", "SMB", "acronym", 6),
    gn("e21", "2026", "date", 6), gn("e22", "Onboarding", "concept", 5), gn("e23", "$1.8M", "money", 5),
    gn("e24", "R&D", "acronym", 5), gn("e25", "Cloud Savings", "concept", 4), gn("e26", "Legal Team", "org", 4),
  ],
  edges: [
    ge("e1", "e8", 9), ge("e1", "e16", 8), ge("e1", "e13", 4), ge("e2", "e11", 8), ge("e2", "e12", 6),
    ge("e2", "e19", 7), ge("e3", "e10", 9), ge("e3", "e6", 8), ge("e3", "e14", 7), ge("e3", "e15", 4),
    ge("e4", "e3", 6), ge("e4", "e5", 5), ge("e4", "e22", 4), ge("e5", "e18", 6), ge("e5", "e26", 4),
    ge("e6", "e20", 5), ge("e7", "e9", 8), ge("e9", "e17", 5), ge("e9", "e26", 3), ge("e10", "e21", 3),
    ge("e14", "e23", 4), ge("e14", "e25", 4), ge("e13", "e8", 3), ge("e24", "e3", 3), ge("e22", "e19", 4),
    ge("e11", "e19", 3), ge("e25", "e5", 3), ge("e15", "e6", 3), ge("e17", "e26", 2), ge("e16", "e8", 2),
  ],
};

/* ── workflows ── */
export const MOCK_WORKFLOWS: WorkflowDef[] = [
  {
    id: "wf-demo-1",
    name: "Upload digest",
    description: "When a document is indexed, summarize it and notify the feed.",
    trigger: "upload",
    enabled: true,
    run_count: 12,
    last_run_at: "2026-07-04T09:12:00Z",
    nodes: [
      { id: "n1", type: "trigger", x: 60, y: 150, data: { label: "On upload" } },
      { id: "n2", type: "agent", x: 320, y: 90, data: { label: "Summarize", agent: "document", prompt: "Summarize in 3 bullet points: {{input}}" } },
      { id: "n3", type: "condition", x: 320, y: 230, data: { label: "Mentions finance?", contains: "finance" } },
      { id: "n4", type: "agent", x: 580, y: 230, data: { label: "Exec brief", agent: "report", prompt: "Write a 100-word executive brief: {{input}}" } },
      { id: "n5", type: "notify", x: 580, y: 90, data: { label: "Notify", message: "New document digest ready ({{workflow}})" } },
    ],
    edges: [
      { from: "n1", to: "n2" }, { from: "n1", to: "n3" },
      { from: "n2", to: "n5" }, { from: "n3", to: "n4" },
    ],
  },
  {
    id: "wf-demo-2",
    name: "Morning KPI brief",
    description: "Analytics digest drafted as an email, on demand.",
    trigger: "manual",
    enabled: true,
    run_count: 31,
    last_run_at: "2026-07-04T06:00:00Z",
    nodes: [
      { id: "n1", type: "trigger", x: 60, y: 150, data: { label: "Manual" } },
      { id: "n2", type: "agent", x: 320, y: 150, data: { label: "KPIs", agent: "analytics", prompt: "Weekly usage KPIs and trends" } },
      { id: "n3", type: "agent", x: 580, y: 150, data: { label: "Draft email", agent: "email", prompt: "Draft an email to leadership with these KPIs: {{input}}" } },
    ],
    edges: [{ from: "n1", to: "n2" }, { from: "n2", to: "n3" }],
  },
];

export function mockRunWorkflow(wf: WorkflowDef, input: string): WorkflowRunInfo {
  const log: WfRunLogEntry[] = [];
  const down = new Map<string, string[]>();
  wf.edges.forEach((e) => down.set(e.from, [...(down.get(e.from) ?? []), e.to]));
  const starts = wf.nodes.filter((n) => n.type === "trigger").map((n) => n.id);
  const queue: [string, string][] = (starts.length ? starts : wf.nodes.slice(0, 1).map((n) => n.id))
    .map((id) => [id, input || "Document 'Q3 Financial Summary' was indexed with 31 chunks."]);
  let payload = input;
  let guard = 0;

  while (queue.length && guard++ < 30) {
    const [id, incoming] = queue.shift()!;
    const node = wf.nodes.find((n) => n.id === id);
    if (!node) continue;
    let output = incoming;
    let proceed = true;
    if (node.type === "agent") output = mockChat(node.data.prompt?.replace("{{input}}", incoming) ?? incoming).answer;
    if (node.type === "condition") proceed = (incoming.toLowerCase()).includes((node.data.contains ?? "").toLowerCase());
    if (node.type === "notify") output = node.data.message?.replace("{{workflow}}", wf.name) ?? "Notified.";
    log.push({
      node: id, type: node.type, label: node.data.label ?? node.type, status: "ok",
      ms: node.type === "agent" ? 400 + Math.floor(Math.random() * 900) : 2 + Math.floor(Math.random() * 20),
      output: node.type === "condition" ? `contains '${node.data.contains}' → ${proceed}` : output.slice(0, 300),
    });
    payload = output;
    if (proceed) (down.get(id) ?? []).forEach((child) => queue.push([child, output]));
  }

  return {
    id: `run-${Date.now()}`,
    status: "ok",
    trigger: "manual",
    input,
    output: payload.slice(0, 1000),
    log,
    duration_ms: log.reduce((s, l) => s + l.ms, 0),
    created_at: new Date().toISOString(),
  };
}

/* ── traces ── */
export const MOCK_TRACES: TraceInfo[] = [
  {
    id: "tr-3f8a21", name: "Summarize the leave policy and email it to HR", kind: "chat",
    user: "maya@eaios.dev", started_at: "2026-07-04T09:41:12Z", duration_ms: 2412, status: "ok",
    spans: [
      { name: "planner", kind: "agent", offset_ms: 2, duration_ms: 118, status: "ok", attrs: { subtasks: 2 } },
      { name: "hybrid_search", kind: "retrieval", offset_ms: 128, duration_ms: 64, status: "ok", attrs: { hits: 6 } },
      { name: "Document Agent", kind: "agent", offset_ms: 124, duration_ms: 1240, status: "ok", attrs: { confidence: 91 } },
      { name: "llm.complete", kind: "llm", offset_ms: 210, duration_ms: 1108, status: "ok", attrs: { model: "llama3.1" } },
      { name: "Email Agent", kind: "agent", offset_ms: 1380, duration_ms: 1010, status: "ok", attrs: { confidence: 84 } },
      { name: "llm.complete", kind: "llm", offset_ms: 1420, duration_ms: 942, status: "ok", attrs: { model: "llama3.1" } },
    ],
  },
  {
    id: "tr-9b02cd", name: "workflow: Upload digest", kind: "workflow",
    user: "admin@eaios.dev", started_at: "2026-07-04T09:12:44Z", duration_ms: 1876, status: "ok",
    spans: [
      { name: "Summarize (document)", kind: "agent", offset_ms: 4, duration_ms: 1211, status: "ok", attrs: { workflow: "Upload digest" } },
      { name: "hybrid_search", kind: "retrieval", offset_ms: 12, duration_ms: 58, status: "ok", attrs: { hits: 6 } },
      { name: "llm.complete", kind: "llm", offset_ms: 84, duration_ms: 1096, status: "ok", attrs: { model: "llama3.1" } },
      { name: "Exec brief (report)", kind: "agent", offset_ms: 1230, duration_ms: 630, status: "ok", attrs: { workflow: "Upload digest" } },
    ],
  },
  {
    id: "tr-c41e77", name: "How are Atlas and Nimbus Cloud related?", kind: "chat",
    user: "dev@eaios.dev", started_at: "2026-07-04T08:55:03Z", duration_ms: 1421, status: "ok",
    spans: [
      { name: "planner", kind: "agent", offset_ms: 1, duration_ms: 92, status: "ok", attrs: { subtasks: 1 } },
      { name: "hybrid_search", kind: "retrieval", offset_ms: 98, duration_ms: 71, status: "ok", attrs: { hits: 6 } },
      { name: "knowledge_graph", kind: "graph", offset_ms: 172, duration_ms: 24, status: "ok", attrs: { path: "Atlas → Priya Sharma → Nimbus" } },
      { name: "Document Agent", kind: "agent", offset_ms: 94, duration_ms: 1290, status: "ok", attrs: { confidence: 88 } },
      { name: "llm.complete", kind: "llm", offset_ms: 240, duration_ms: 1130, status: "ok", attrs: { model: "llama3.1" } },
    ],
  },
];

/* ── meeting assistant (demo minutes — mirrors the backend mock) ── */
export function mockMinutes(transcript: string): string {
  const sentences = transcript.replace(/\n/g, " ").split(".").map((s) => s.trim()).filter(Boolean);
  const actionish = sentences.filter((s) => /will |action|todo|follow up|send|prepare|schedule/i.test(s));
  const decisionish = sentences.filter((s) => /decided|agree|approved|go with|choose/i.test(s));
  const lines = [
    "## Summary",
    `The meeting covered ${Math.min(sentences.length, 5)} main points across ${transcript.split(/\s+/).filter(Boolean).length} words of discussion. ` +
    "Key threads are captured below; connect the live backend with an LLM key for reasoning-based minutes.",
    "", "## Decisions",
    ...(decisionish.slice(0, 4).map((s) => `- ${s}.`) as string[]).concat(decisionish.length ? [] : ["- No explicit decisions detected."]),
    "", "## Action Items",
    ...(actionish.slice(0, 5).map((s) => `- [unassigned] ${s}.`) as string[]).concat(actionish.length ? [] : ["- No explicit action items detected."]),
  ];
  return lines.join("\n");
}

/* ── document analyzers (demo scorecards) ── */
export function mockAnalyze(docId: string, kind: string, title: string) {
  const base = {
    resume: {
      verdict: "Screen-worthy technical profile", score: 82,
      highlights: [
        { label: "Skills detected", value: "python, react, sql, docker", status: "good" as const },
        { label: "Experience signal", value: "senior-level phrasing across 6 chunks", status: "good" as const },
        { label: "Contact", value: "email present", status: "good" as const },
        { label: "Gaps", value: "no dates on last role", status: "warn" as const },
      ],
      summary: "Strong core-stack coverage with production system mentions. Recommend a systems-design screen; verify the most recent role's timeline in the phone screen.",
    },
    contract: {
      verdict: "3 risk-bearing clause types flagged", score: 61,
      highlights: [
        { label: "Risk clauses", value: "termination, liability cap, arbitration", status: "warn" as const },
        { label: "Liability cap", value: "$50,000", status: "warn" as const },
        { label: "Term", value: "12 months, auto-renew", status: "good" as const },
        { label: "Payment", value: "net-30", status: "good" as const },
      ],
      summary: "Standard MSA shape, but the liability cap is low relative to contract value and the arbitration venue favours the vendor. Legal review recommended before signature.",
    },
    invoice: {
      verdict: "Totals located — verify against PO", score: 88,
      highlights: [
        { label: "Total", value: "$12,450.00", status: "good" as const },
        { label: "Due date", value: "Aug 15, 2026 (net-30)", status: "good" as const },
        { label: "Line items", value: "7 items, no duplicates", status: "good" as const },
        { label: "Tax", value: "GST missing HSN code", status: "warn" as const },
      ],
      summary: "Arithmetic checks out and vendor details match the master record. One tax-field gap to fix before booking; otherwise ready for approval.",
    },
    auto: {
      verdict: "General business document", score: 74,
      highlights: [
        { label: "Type", value: "policy / report hybrid", status: "good" as const },
        { label: "Key figures", value: "3 amounts, 2 dates detected", status: "good" as const },
        { label: "Follow-ups", value: "2 sections reference missing appendices", status: "warn" as const },
      ],
      summary: "Readable, well-structured document. The referenced appendices are not attached — request them before relying on the totals.",
    },
  }[kind as "resume" | "contract" | "invoice" | "auto"] ?? {
    verdict: "General document", score: 70, highlights: [], summary: "Demo analysis.",
  };
  return { doc_id: docId, title, kind, engine: "demo", ...base };
}
