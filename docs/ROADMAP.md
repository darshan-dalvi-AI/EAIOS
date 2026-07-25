# EAIOS — 16-Week Build Roadmap

Weeks 1–4 are **already delivered** by the foundation in this repo. Each later phase is independently demoable — you always have a working system for reviews.

## Phase 0 · Foundation (weeks 1–4) ✅ shipped

JWT auth + RBAC + audit · SQLAlchemy schema · hybrid RAG (parse→chunk→embed→index, BM25+vector RRF, citations, confidence) · 8-agent orchestrator with planner decomposition · NL→SQL guardrails · OS-metaphor frontend (boot, login, window manager, dock, ⌘K palette, 8 apps, live/demo duality) · Docker Compose · smoke tests · CI.

## Phase 1 · Real models (weeks 5–6)

- Ollama integration end-to-end (`LLM_PROVIDER=ollama`, llama3.1 + nomic-embed-text); measure answer quality vs mock.
- `sentence-transformers` BGE-small embeddings; re-index seed corpus; add eval script (retrieval hit-rate on 20 hand-written Q/A pairs).
- Wire Qdrant in compose as default; keep in-memory fallback.
- **Demo**: same questions, visibly better answers; eval table in README.

## Phase 2 · True multimodality (weeks 7–8)

- `unstructured` (or Docling) parser behind `parsers.py`; table extraction to markdown.
- PaddleOCR/Tesseract for scanned docs; image captioning via Qwen2.5-VL or LLaVA through Ollama (Vision AI module).
- Chart/diagram QA: route image chunks to the VLM at answer time.
- **Demo**: upload a scanned invoice + a chart screenshot, ask questions about both.
- ✅ **2026-07-12 — advanced structured parsing** (`rag/tables.py`): complex/nested tables (native docx/pptx table objects incl. nested, xlsx sheets, csv, pdf/txt line-grids) are extracted as *structured data* and materialized into **real SQL tables** (`dt_*`) that the SQL Agent queries directly — bypassing text chunking; each table also indexes a summary chunk so RAG can cite it. Schema explorer (`GET /api/agents/sql/schema`) and the SQL Studio app show them with provenance.

## Phase 3 · LangGraph + observability (weeks 9–10)

✅ **Shipped 2026-07-05**
- Orchestrator rebuilt as a `StateGraph` (planner → conditional dispatch → agent nodes → merger) in `agents/graph.py` — LangGraph API semantics implemented dependency-free (swap to the real lib is a one-line import); REST contract unchanged, legacy sequential path kept as automatic fallback.
- Agent-to-agent messaging: shared graph state dict (typed channels), chained step context.
- Tracing core (`core/tracing.py`): every chat request + workflow run records a span waterfall (agent/llm/retrieval/graph) served at `/api/traces` and rendered in the new **Traces** OS app; optional OTel-OTLP + Langfuse exporters activate via env keys.
- **Demo**: open Traces after a compound question — full waterfall with per-span attrs.

## Phase 4 · Real-time collaboration (weeks 11–12)

✅ **Shipped 2026-07-05**
- FastAPI WebSocket layer (`/api/ws`, JWT in query) + in-process hub (Redis pub/sub slot-in for multi-replica): presence avatars in the menu bar, live `agent.step` / `doc.status` / `workflow.*` / `chat.message` events replacing the mock feed in the Agents app; REST replay at `/api/events/recent`.
- Frontend realtime client (`lib/ws.ts`): auto-reconnect with backoff, ping keep-alive; vite proxy `ws: true`.
- Deferred: CRDT (Yjs) shared-notes app (stretch).
- **Demo**: two browsers logged in as different users — both appear in presence; ask in one, watch the agent feed stream in the other.

## Phase 5 · Workflow builder + knowledge graph (weeks 13–14)

✅ **Shipped 2026-07-05**
- **Automations** OS app: hand-rolled drag-and-drop node canvas (trigger / agent / condition / notify, bezier edges, inspector panel) → JSON DAG stored via `/api/workflows` → executed by the same agent runtime (`services/workflows.py`); triggers: manual + on-upload (schedule slot ready). Runs are traced + streamed live.
- Entity extraction on ingest (`services/kgraph.py`, deterministic NER — spaCy/LLM slot-in) → entities + co-occurrence edges in SQL (Neo4j slot-in); **Graph** OS app with custom force-directed SVG constellation; graph-augmented retrieval answers "how are X and Y related" with connection paths + cited evidence.
- **Demo**: build "on upload → summarize → notify" visually and upload a file; ask a relational question; explore the constellation.

## Phase 6 · Production hardening (weeks 15–16)

✅ **Shipped 2026-07-05** (deploy-to-cloud is the only step left — needs a cluster)
- Kubernetes: **Helm chart** `deploy/helm/eaios` — backend Deployment + HPA (CPU 65%, 2→10), Qdrant StatefulSet + PVC, frontend, TLS ingress (cert-manager annotations, WS-friendly timeouts), nightly `pg_dump` **backup CronJob** with retention; raw manifests kept in `deploy/k8s.yaml`.
- CI/CD: GitHub Actions — pytest + frontend build + Docker buildx; **pushes images to GHCR on main** (built-in token); manual-trigger **staged Helm deploy** gated by a `production` environment + `KUBE_CONFIG` secret.
- **Rate limiting**: token buckets per user/IP (login 20/min, chat 60/min, upload 60/hr…), 429 + Retry-After, in-memory default, **Redis-backed across replicas** when `REDIS_URL` set.
- **Load tested** (`backend/tests/load/`: locustfile + zero-dep httpx harness): 100 concurrent users → **98 req/s, 0 errors, p50 754 ms, p95 2.1 s** on a single worker + SQLite. Found & fixed a real defect: default connection pool exhausted at ~60 users → widened pool + SQLite WAL/busy-timeout.
- Fine-tuning track (stretch): still open — export thumbs-up answers → LoRA on Llama 3 → serve via Ollama.
- **Demo**: run the load test live while `kubectl get hpa -w` shows replicas scaling; CI green wall on GitHub.

## Post-roadmap upgrades · advisory batch 2 ✅ shipped 2026-07-12

- **Advanced document parsing** — structured tables → real SQL tables → SQL Agent (see Phase 2 note above).
- **Privacy & data protection** — granular PII audit flag: knowledge-graph entities are classified (`person` / `email` / `phone` = sensitive); any agent, graph query, or MCP client touching them writes a `pii.access` audit entry and pushes a `security.pii` event to the live feed. Entity types now refine on new evidence (`concept` → `person` when a title like *Dr.* appears). wss:// was already covered: the WS endpoint rides the same TLS ingress/host as HTTPS.
- **Checkpointer memory (state persistence)** — LangGraph's checkpointer interface implemented and DB-backed (`agents/checkpointer.py`, `graph_checkpoints` table): orchestrator state is saved after **every super-step**, keyed by conversation; an interrupted run (LLM outage, restart, closed laptop) resumes from the saved node when the same request is retried — completed agents are not re-run. Toggle: `GRAPH_CHECKPOINTS`.
- **SQL Studio goes live** — the app now talks to the real backend (NL→SQL + live schema explorer incl. extracted `dt_*` tables with provenance) and keeps the demo fallback.

## Post-roadmap upgrades · batch 3 ✅ shipped 2026-07-12

- **MIT LICENSE** at repo root (the Terms dialog references it).
- **Report exports** — any agent answer downloads as **PDF** (dependency-free hand-assembled PDF 1.4 writer: Helvetica/Courier, wrapping, bullets, page footers) or **DOCX** (python-docx); `POST /api/reports/export`, buttons on chat bubbles.
- **Scheduled workflows** — `trigger=schedule` + per-workflow interval (trigger node `every` minutes, editable in the Automations inspector); async scheduler loop in the app lifespan fires due runs. **Notification center**: menubar bell with unread badge + event history, plus transient toasts for workflow/security/system events.
- **AI Meeting Assistant** (12th OS app) — record via Web Speech or paste a transcript → structured minutes (summary / decisions / action items) → optionally saved and indexed into the knowledge base.
- **Model Arena** — Settings (admin): one prompt, two OpenRouter models side by side with per-model latency; `POST /api/admin/compare` runs them in parallel threads.
- **Document analyzers** — Resume / Contract / Invoice / Auto quick-actions in Knowledge: LLM strict-JSON scorecards with a deterministic heuristic fallback (amounts, dates, risk clauses, skills) so demo mode always answers.

## Post-roadmap upgrades · batch 4 ✅ shipped 2026-07-12

- **Video Call** (13th OS app, `apps/VideoApp.tsx`) — built-in **WebRTC** 1:1 video calling with AI features:
  - Signaling rides the existing realtime WebSocket as point-to-point `rtc.*` frames (relayed to one user, never broadcast/buffered); media is peer-to-peer, STUN-only, never touches the server.
  - **Live captions** (Web Speech) for both sides, exchanged over the signaling channel so each participant sees a merged transcript.
  - **Auto Minutes-of-Meeting** on hang-up: the merged caption transcript is sent through the Meeting agent → summary / decisions / action items, optionally saved to the knowledge base.
  - **Virtual backgrounds & effects** via a canvas pipeline (portrait blur, noir, aurora wash, nebula backdrop) — the outgoing track is always the canvas, so switching effects never renegotiates the connection.
  - Screen share (`replaceTrack`), mute / camera toggles, talk-time balance meter, incoming-call ring with accept/decline.
  - Verified: 3 signaling-relay unit tests + a headless two-browser call (ring → accept → both live → mid-call effect switch → hang-up → both return to idle) all green; pixel-level media flow needs a real browser/camera.

## Post-roadmap upgrades · batch 5 ✅ shipped 2026-07-12 (the "Google/Microsoft would add this" set)

Four platform features that shift EAIOS from "AI demo" toward "enterprise platform":

- **Connectors** (`services/connectors.py`, Connectors app) — pull external data into the same RAG pipeline as uploads. A bundled **Sample Workspace** (demo Gmail threads + Drive docs incl. a structured CSV) works with zero setup; **Google Drive** and **Gmail** sync real data given a user-supplied OAuth access token (Drive API v3 export / Gmail API). The full OAuth consent flow is documented in docs/DEPLOY.md. Synced items are parsed, chunked, embedded, entity-linked and (for tables) materialised as SQL — searchable and citable like any upload.
- **Agent Studio** (`agents/custom_agent.py`, `routes/studio.py`, Studio app) — compose a custom agent with **no code**: a name, a system prompt, and tool toggles (knowledge-base RAG, web search). Custom agents run through the same `BaseAgent` contract (AgentRun telemetry, tracing) and are selectable in Chat's Route picker. RBAC: only the owner or an admin can edit/delete.
- **NL-to-BI Dashboards** (`services/charts.py`, Dashboards app) — describe a chart in English; the SQL agent writes and runs a safe query, a heuristic infers the chart type (bar/line/pie/table) and axes, and it renders with Recharts. Pin charts to a persistent dashboard grid.
- **Multi-party video** — the Video app is now a **mesh room**: start a call and invite more people (each joiner offers to everyone already in the room → full mesh), rendered as a participant grid. **Live Minutes-of-Meeting**: a "MoM now" button generates minutes mid-call from the running transcript, in addition to the auto-MoM on hang-up.
- 16 OS apps total. Verified: **58/58 backend pytest** (+test_batch5: chart inference/endpoint/pin, studio CRUD/run/chat-route/RBAC, connector sample-sync + drive-token guard), tsc clean, both builds, **10/10 + 9/9 headless QA** (all four apps end-to-end; two-user mesh call state machine + MoM-now).

## Post-roadmap upgrades · batch 6 ✅ shipped 2026-07-19 ("God Mode" batch — 9 features)

**18 OS apps.** (1) **Mobile mode** — ≤740px windows go full-screen (menubar→app→dock tab bar), dock scrolls horizontally; hand the examiner a phone. (2) **Guided tour** — 6-step spotlight overlay on first login (localStorage flag), replay from Settings. (3) **Website connector** — crawl any URL breadth-first (same host, ≤8 pages, private-IP/SSRF blocklist) into the RAG pipeline. (4) **Tasks app** — kanban whose cards auto-create from meeting-minutes action items (`tasks_created` returned by /agents/meeting); drag or arrow between columns, assign to online users. (5) **AI usage metering** — every chat/meeting logs a `UsageEvent`; Admin → AI usage shows requests/tokens/est-cost per user & model (30d) with honest "estimated" labeling. (6) **Global Search app** — one query fans out to documents, hybrid-RAG passages, KG entities, `dt_*` tables and the user's own messages; menubar 🔍 opens it. (7) **Compliance** — GET /me/export (full JSON bundle), DELETE /me/data (chats/tasks/charts/usage; account+shared docs kept), `RETENTION_DAYS` env auto-purges old conversations in the scheduler tick. (8) **Live RAG eval** — /analytics/rag-eval reruns the CI eval set live (hit-rate@3, MRR) and renders as an Analytics card. (9) **"Hey EAIOS" wake word** — continuous Web-Speech listener (opt-in toggle, chime + opens Chat).
Verified: **65/65 pytest** (+6 batch-6 tests: tasks CRUD/RBAC, meeting→tasks, search groups, export/erase round-trip, metering+eval, website SSRF guard), tsc clean, both builds, **13/13 headless QA** incl. 390px mobile viewport.

## Post-roadmap upgrades · batch 7 ✅ shipped 2026-07 (production-hardening + reach)

- **Cloud persistence** — database migrated from ephemeral SQLite to **Supabase Postgres** (`DATABASE_URL`, session pooler); uploaded files mirrored to **Supabase Storage** (`core/storage.py`, `trust_env=False` proxy-safe, local-disk fallback). Data + files now survive every redeploy. Docs in DEPLOY.md.
- **Admin 'hire a teammate'** — admins create manager/employee/admin accounts (email + generated password + copy-ready invite) from the Admin → Users tab (`POST /users`, PBKDF2, audited).
- **HR role** — fourth RBAC role for people operations: hire/manage line staff (managers/employees) via a scoped "HR console" (Users + Access tabs only); can't touch model keys, admin/HR accounts, or grant admin. Enforced by `require_admin_or_hr` + assignment guardrails. Seeded demo user `riya@eaios.dev`.
- **Installable app (PWA)** — "Download app" (landing) / "Install as app" (login) buttons trigger the native install prompt via `beforeinstallprompt`; standalone install on Windows/Mac/Android with 192/512 PNG icons + maskable; iOS gets add-to-home-screen instructions. Offline shell via the v3 service worker.
- **Confidential Computing (TEE) design** — `docs/CONFIDENTIAL_COMPUTING.md`: threat model + AMD SEV-SNP attestation architecture, incl. the LLM-boundary insight.
- **Keep-alive** — GitHub Actions cron pings `/api/health` every ~10 min so the free Render instance never cold-starts.
- **Polish** — video self-view shows the true (un-mirrored) camera; login role ordering admin → HR → manager → employee; global error boundary self-heals; connector errors surface cleanly.
- Verified: **73/73 backend pytest**, tsc clean, both builds, headless A–Z (18 apps + PWA + roles + mirror) all green; live-site integration incl. Supabase read/write and file-in-storage confirmed.

## Post-roadmap upgrades · batch 8 ✅ shipped 2026-07-24 (multi-tenant SaaS — "sell to many companies")

Turns EAIOS from one deployment into a product any company can self-serve — one hosted app, isolated workspaces per company.

- **Company signup** — "Create your workspace →" on the login screen (`POST /auth/signup`): a company name + admin details spin up a new `Organization` (collision-free slug) and its first admin in one call, returning a scoped token. Login/register/JWT now carry the org; the workspace name shows in the menu bar.
- **Tenant isolation at the ORM layer** — a `TenantMixin` puts `org_id` on all 20 domain tables; a `do_orm_execute` hook auto-scopes **every** read (`with_loader_criteria`) and a `before_flush` hook auto-stamps **every** write with the request's org. Isolation can't be forgotten per-query — it's structural. Activated per-request from the JWT (`deps.py` sets `db.info["org_id"]`), and propagated into RAG ingest, the seeder, and the workflow scheduler.
- **Raw-SQL guard for the SQL agent** — the NL→SQL agent executes `text()` SQL, which the ORM hook can't see, so it gets its own **fail-closed** `_tenant_scope`: every tenant table is rewritten into `(SELECT * FROM t WHERE org_id = :org) AS t`, the tenant registry (`organizations`) is denied, and any shape it can't provably scope (aliases, comma-joins) is rejected rather than run. A workspace can never read another's rows even by asking the SQL agent directly.
- **First-run Setup Guide** — new company admins get a dismissible onboarding checklist (invite team → add knowledge → connect tools → ask the AI → install app), progress persisted per workspace, reopenable from Settings.
- **Workspace lifecycle (suspend / delete)** — `Organization.status` + `routes/orgs.py`. A **platform-owner console** (Admin → Workspaces, gated by `PLATFORM_OWNER_EMAILS`; unset = endpoint disabled for everyone, so the published demo login can't reach it) lists every tenant with live row counts and can **suspend** (members blocked at login, all data kept) or **permanently delete** one. A company's own admin can close their workspace from a **Danger zone**; the shared demo workspace is protected. Deletion is a true cascade — 19 tenant tables in child→parent order, plus the workspace's `dt_*` tables and its uploaded files — and runs through `tenancy.unscoped()`, since the owner sits in a *different* workspace and would otherwise be filtered away from the rows being removed.
- **Legacy NULL-org fix (security)** — rows predating multi-tenancy had `org_id IS NULL`, and a *user* with no org received **no read filter at all** (the hook skips when the session has no org), so a legacy account could read every company's data — reproduced on the live database, where `admin@eaios.dev` returned another workspace's user. `_backfill_null_orgs()` now adopts every orphan row into the default demo workspace at boot, restoring the invariant "every row belongs to exactly one workspace".
- **Supabase surface hardening** — Supabase auto-publishes every `public` table through its PostgREST API, raising a CRITICAL *RLS Disabled in Public* advisory per table. Since EAIOS never uses that API, the app now closes it on every boot (`harden_public_schema`): RLS enabled with **no policies** (deny-by-default for `anon`/`authenticated`) plus those roles' grants revoked, including via `ALTER DEFAULT PRIVILEGES` so future tables — and the runtime `dt_*` spreadsheet tables, hardened at creation — are never exposed. Safe by construction: the app's role owns every table and carries `BYPASSRLS`, and no table uses FORCE RLS. Verified live on the production project: **21/21 tables RLS-on, 0 API grants, 0 advisories**, with login/reads/writes unaffected. One-shot script: `docs/supabase_harden.sql`.
- Verified: **94/94 backend pytest** (+`test_workspace_admin.py` 9: console disabled with no owner configured, company admin can't see/suspend/delete another workspace, owner listing with counts, suspend blocks login + reactivate restores it, exact-name confirmation required, owner delete removes the tenant *and leaves the neighbouring workspace's tasks/docs/chats intact*, self-delete, non-admin refused, demo workspace protected) + **21/21 headless QA** (owner sees the tab and non-owners don't, suspend→403→reactivate→200, delete button stays disabled until the name matches, deleted tenant's login turns 401, self-delete drops to the login screen, demo admin now has a workspace); +`test_db_hardening.py` 6: SQLite no-op, exact DDL emitted per table, default-privilege revoke, never-blocks-startup, dt_* hardened on creation; +`test_tenancy.py`: signup-creates-isolated-org, two-companies-can't-see-each-other across users/docs/tasks/chat/search + cross-org PATCH→404, RAG scoped, SQL-agent cross-org count/rows blocked, guard rewrite/reject units, demo login intact), tsc clean, both builds, **9/9 SaaS headless QA** (signup→empty isolated workspace, org name in menu bar, admin sees only its users, live two-company task isolation, demo login still works).

## Deliverables checklist

Report + architecture diagrams (docs/) · demo video script: boot → login → ⌘K → RAG answer with citations → compound request planner demo → SQL Studio → admin audit → kill backend mid-demo to show demo-mode resilience (judges love this) · GitHub repo with CI badge · deployed URL.
