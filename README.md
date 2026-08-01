# K-OS — A Knowledge Operating System for the Enterprise

<!-- Repo path stays /EAIOS until the GitHub repository itself is renamed;
     changing it here first only produces a broken badge. -->
![CI](https://github.com/darshan-dalvi-AI/EAIOS/actions/workflows/ci.yml/badge.svg)

**A hybrid multimodal RAG, multi-agent AI platform for enterprise knowledge — presented as a literal operating system in the browser.**

Boot screen → login → desktop with a taskbar, draggable windows, and a Ctrl+K command palette. Nineteen "apps" (AI Chat, Knowledge, Agents, **Graph**, **Automations**, **Traces**, Search, Tasks, SQL Studio, Analytics, Dashboards, Agent Studio, Connectors, Meeting, Video, **Code**, Admin, Terminal, Settings) run as windows on top of a FastAPI + multi-agent + hybrid-RAG backend with realtime WebSocket presence. Which apps sit on the taskbar adapts to the workspace's industry; the rest stay one click away in the drawer.

> Final-year B.E. Computer Engineering capstone · React + TypeScript + FastAPI + Qdrant + PostgreSQL · runs fully offline with zero API keys

---

## Why it's different

Most "enterprise chatbot" projects are a chat box over an API call. K-OS is:

- **An OS metaphor UI** — window manager, dock with magnification, boot sequence, command palette, faux shell. No enterprise tool ships like this; it demos unforgettably.
- **Genuinely grounded RAG** — hybrid retrieval (dense vectors + BM25, fused with Reciprocal Rank Fusion), citation chips with relevance meters, per-answer confidence scores.
- **A real multi-agent system** — a Planning Agent decomposes compound requests and routes subtasks across 9 agents (Planning, Document, SQL, Research, Email, Report, Analytics, Memory, Coding), each recorded in an observability table.
- **Zero-dependency dev mode** — SQLite + in-memory vector store + a deterministic extractive "mock LLM" mean the entire platform runs with no Docker, no GPU, no keys. Swap one env var to move to Postgres + Qdrant + Ollama/GPT/Claude.
- **Multi-tenant SaaS** — any company can self-serve: "Create your workspace" on the login screen spins up an isolated tenant with its own admin, users and data. Isolation is enforced at the ORM layer (auto-scoped reads + auto-stamped writes), so one company can never see another's documents, chats, tasks or search results — proven by a dedicated `test_tenancy.py` suite. The SQL agent, which runs raw SQL, gets its own fail-closed guard that rewrites every tenant table into an org-scoped subquery. One deploy, many companies.
- **Guided onboarding** — a new company admin lands on a Setup Guide checklist (invite team → add knowledge → connect tools → ask the AI → install the app), reopenable from Settings.
- **Security done properly for a student project** — PBKDF2 password hashing, stdlib HS256 JWTs, RBAC guards (admin · HR · manager · employee), SELECT-only + org-scoped SQL guardrails, append-only audit log.
- **Graph-orchestrated agents with real observability** — the orchestrator is a StateGraph (LangGraph semantics, dependency-free); every chat/workflow run records a span waterfall you can open in the Traces app (OTel/Langfuse exporters optional).
- **A knowledge graph that builds itself** — entities + co-occurrence edges extracted at ingest, explored in a force-directed constellation (Graph app), and used to answer "how are X and Y related?" with paths + cited evidence.
- **Visual automations** — drag-and-drop workflow canvas (trigger → agents → conditions → notify) executed by the same agent runtime, with live-streamed runs; fires automatically on document upload.
- **Realtime presence** — WebSocket hub pushes who's online + live agent activity to every window.
- **Real collaborative editing, not a shared textarea** — the Code app holds the file as a Yjs CRDT, so several people can type in the same file at once and every browser converges to identical text regardless of the order updates arrive in. The server relays binary updates and never merges anything. On top of it: content-addressed version control (commits, branches, diffs, restore), an AI assistant scoped to your selection, and a Run button.
- **Code execution that cannot touch the server** — Python and JavaScript run in a frame sandboxed to an *opaque origin*: no cookies, no storage, no parent DOM, and CORS rejects any call to the K-OS API. That isolation is the point, because in a shared editor the code you press Run on may have been typed by a colleague. Python is CPython on WebAssembly, so `import numpy` works; runaway programs are killed by a timeout rather than freezing the tab.

## Quickstart

### Path 1 — instant (no external services)

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # bootstraps admin automatically
python -m app.seed                             # optional: demo docs + users

# frontend (new terminal)
cd frontend
npm install
npm run dev                                    # http://localhost:5173
```

### Path 2 — full stack via Docker

```bash
cp .env.example .env
docker compose up --build                      # frontend :3000 · api :8000 · qdrant :6333
docker compose --profile local-llm up          # + Ollama for local Llama 3
```

### Path 3 — live on the internet (free)

One-container build (`Dockerfile.web`) + Render blueprint (`render.yaml`):
push to GitHub → render.com → New → Blueprint → Apply → paste a free Groq key
for real Llama 3.1 answers. Full steps: [docs/DEPLOY.md](docs/DEPLOY.md).

**Sign up your company** — on the login screen, click **"Create your workspace →"**, enter a company name, your name, a work email and password. You become the admin of a brand-new, empty, isolated workspace — then use the Setup Guide to invite your team.

**Demo logins** — `admin@eaios.dev / admin12345` (admin) · `manager@eaios.dev / demo12345` · `hr@eaios.dev / demo12345` · `employee@eaios.dev / demo12345`

On the public deployment these open a **private throwaway workspace** rather than a
shared one, so two visitors never see each other's uploads — see `DEMO_SANDBOX` in
[`.env.example`](.env.example). Reloading the page starts a fresh one.

The frontend auto-detects the backend. If it's down, every app still works in **Demo mode** on realistic mock data — the login screen tells you which mode you're in.

## Architecture

```
React 18 + TS (OS shell: windows/dock/palette)
        │  REST /api   WS /api/ws (presence · CRDT relay)
FastAPI ──► Orchestrator ──► Planning Agent ──► 9 specialist agents
        │                         │
        │                  Hybrid RAG engine
        │            (parse→chunk→embed→index)
        │                 │              │
   PostgreSQL/SQLite   Qdrant / in-mem   LLM layer
   (users, docs,       (vectors, RRF     (mock │ Ollama │
    chats, audit,       + BM25 fusion)    OpenAI │ Anthropic)
    code, commits)

   Code execution is deliberately NOT in this diagram: it happens in a
   sandboxed opaque-origin frame in the user's browser, never server-side.
```

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_REFERENCE.md](docs/API_REFERENCE.md) · Plan: [docs/ROADMAP.md](docs/ROADMAP.md)

## Repository layout

```
backend/app/
  core/        config · JWT + PBKDF2 security · database (+RLS) · events (WS hub) · collab (CRDT relay)
               · headers (CSP) · storage · tracing (spans)
  api/routes/  auth · users · documents · chat · agents · admin · analytics · graph · workflows · traces
               · search · tasks · me · orgs · projects (code + VCS) · runner (execution sandbox)
               · dashboards · studio · connectors · reports · ws
  rag/         parsers · chunking · embeddings · vectorstore · hybrid retrieval · tables · pipeline
  agents/      base · registry · graph (StateGraph runtime) · orchestrator · checkpointer
               · 9 agent implementations
  services/    kgraph · workflows (DAG executor) · vcs (content-addressed commits) · industries
               · connectors · charts · analyze · reports · audit
  llm/         provider abstraction (mock/ollama/openai/anthropic)
  seed.py      demo users + documents through the real pipeline
backend/tests/ 385 tests — auth · RBAC · JWT · tenancy isolation · chunking · SQL guardrails
               · graph engine · KG · workflows · WS · concurrent editing · code-runner sandbox
frontend/src/
  os/          BootScreen · LoginScreen · Desktop · MenuBar · Dock (industry-aware) · Window
               · CommandPalette · LandingPage
  apps/        Chat · Knowledge · Agents · Graph · Automations · Traces · Search · Tasks · SQLStudio
               · Analytics · Dashboards · Studio · Connectors · Meeting · Video · Code · Admin
               · Terminal · Settings
  lib/         api client (live/demo fallback) · ws realtime client · runCode (sandbox client)
               · mock data layer
docs/          architecture · API reference · roadmap · demo script · deploy · viva kit
```

## Feature checklist (spec coverage)

| Module | Status |
|---|---|
| JWT auth + RBAC + audit log | ✅ implemented |
| Hybrid multimodal RAG (PDF/DOCX/PPTX/XLSX/CSV/images) | ✅ implemented (OCR pluggable) |
| Multi-agent system (9 agents, planner included) | ✅ implemented |
| NL→SQL with safety guardrails | ✅ implemented |
| Long-term memory | ✅ implemented |
| Internet search agent | ✅ implemented (DuckDuckGo IA) |
| Admin panel (users, audit, models, RBAC matrix) | ✅ implemented |
| Analytics dashboards | ✅ implemented |
| Docker + compose + CI | ✅ implemented |
| Voice AI (mic input + read-aloud) | ✅ implemented |
| Vision VLM captioning (via Ollama vision models) | ✅ implemented |
| Graph orchestrator (StateGraph, LangGraph semantics) | ✅ implemented |
| Dynamic semantic routing (LLM router → parallel fan-out) | ✅ implemented |
| Self-correcting SQL agent (reflection retry loop) | ✅ implemented |
| Human-in-the-Loop approval node (checkpointer-backed) | ✅ implemented |
| Automated RAG eval gate in CI (hit-rate + MRR) | ✅ implemented |
| Choose AI model live: GPT/Claude/Gemini/DeepSeek/Qwen/Llama/Phi via OpenRouter | ✅ implemented |
| Realtime collab (WS presence + live agent feed) | ✅ implemented |
| Knowledge graph + graph-augmented retrieval | ✅ implemented |
| Visual workflow builder (Automations) | ✅ implemented |
| Observability (Traces app; OTel/Langfuse exporters) | ✅ implemented |
| Landing page (hero, features, tech, architecture) | ✅ implemented |
| Chat streaming (SSE) + stop/regenerate/export + code blocks | ✅ implemented |
| Coding Agent (9th agent) | ✅ implemented |
| MCP server (`python -m app.mcp_server`) | ✅ implemented |
| Dark/Light mode + PWA offline shell | ✅ implemented |
| Kubernetes: Helm chart + HPA + TLS + backup CronJob | ✅ deploy/helm/eaios (raw manifests in deploy/k8s.yaml) |
| Rate limiting (token buckets, Redis-ready) | ✅ implemented |
| Load tested — 100 concurrent users, 0 errors | ✅ 98 req/s, p95 2.1s (single worker, SQLite) |
| CI/CD: tests + GHCR image push + gated Helm deploy | ✅ .github/workflows/ci.yml |
| Structured table extraction → real SQL tables (nested docx, pdf grids, xlsx/csv) | ✅ implemented (`rag/tables.py`) |
| Granular PII audit flag (agent access to person/email/phone entities) | ✅ implemented (`pii.access` + live `security.pii` event) |
| LangGraph checkpointer — DB-persisted graph state, resume after interruption | ✅ implemented (`agents/checkpointer.py`) |
| Live SQL Studio (schema explorer + NL→SQL against the real backend) | ✅ implemented |
| Report exports — download any agent answer as PDF/DOCX (zero-dep PDF writer) | ✅ implemented (`services/reports.py`) |
| Scheduled workflows (interval trigger) + notification bell & toasts | ✅ implemented |
| AI Meeting Assistant — record/paste → minutes → save to Knowledge (12th app) | ✅ implemented |
| Model Arena — same prompt, two OpenRouter models side by side with latency | ✅ implemented |
| Document analyzers — Resume / Contract / Invoice scorecards | ✅ implemented (`services/analyze.py`) |
| Video Call — WebRTC **multi-party mesh** calls with AI: live captions, live + on-hangup Minutes-of-Meeting, virtual backgrounds/effects, screen share | ✅ implemented (`apps/VideoApp.tsx`, `rtc.*` WS relay) |
| NL-to-BI **Dashboards** — describe a chart in English → SQL agent → rendered chart, pin to a dashboard | ✅ implemented (`services/charts.py`, Recharts) |
| **Agent Studio** — no-code custom agents (system prompt + RAG/web tools); appear in Chat's route picker | ✅ implemented (`agents/custom_agent.py`, `routes/studio.py`) |
| **Connectors** — Gmail / Google Drive (OAuth token) + bundled Sample Workspace → RAG pipeline | ✅ implemented (`services/connectors.py`) |
| **Mobile mode** — full-screen apps + scrollable dock ≤740px; same platform on a phone | ✅ implemented (CSS media layer) |
| **Guided onboarding tour** — first-run spotlight walkthrough, replayable from Settings | ✅ implemented (`os/Tour.tsx`) |
| **Website connector** — paste a URL, crawl same-domain pages into the RAG pipeline (SSRF-guarded) | ✅ implemented (`services/connectors.py`) |
| **Tasks kanban** — meeting action items auto-become cards; drag/move/assign (18th app) | ✅ implemented (`apps/TasksApp.tsx`, `routes/tasks.py`) |
| **AI usage & cost metering** — requests/tokens/est. cost per user & model in Admin | ✅ implemented (`UsageEvent`, `/analytics/ai-usage`) |
| **Global search hub** — one query across docs, passages, entities, tables & chats (17th app) | ✅ implemented (`apps/SearchApp.tsx`, `/search`) |
| **Compliance pack** — GDPR export / erase-my-data + `RETENTION_DAYS` auto-purge | ✅ implemented (`routes/me.py`) |
| **Live RAG eval card** — hit-rate@3 + MRR run live in Analytics | ✅ implemented (`/analytics/rag-eval`) |
| **"Hey K-OS" wake word** — hands-free open-the-assistant (Settings toggle) | ✅ implemented (`os/WakeWord.tsx`) |
| **Supabase Storage** for uploads — files mirrored to cloud object storage, survive redeploys (local-disk fallback, zero-config dev) | ✅ implemented (`core/storage.py`) |
| **Confidential Computing (TEE) design** — threat model + AMD SEV-SNP attestation architecture for data-in-use protection | 📋 design doc ([docs/CONFIDENTIAL_COMPUTING.md](docs/CONFIDENTIAL_COMPUTING.md)) |
| **HR role** — people-ops console: hire/manage staff (managers/employees), scoped RBAC (no model keys / can't touch admins) | ✅ implemented (`require_admin_or_hr`) |
| **Installable app (PWA)** — one-click 'Download app' installs K-OS as a standalone app on Windows/Mac/Android (PNG icons, manifest, offline shell) | ✅ implemented (`lib/pwa.ts`, `InstallButton`) |
| **Code app** — Monaco editor, file tree, tabs, syntax highlighting (19th app) | ✅ implemented (`apps/CodeApp.tsx`, `routes/projects.py`) |
| **Upload files / open a folder** — folder picker + drag-and-drop; a folder becomes its own project with paths preserved. Dependencies, build output, lockfiles and binaries are filtered out (client-side to stay responsive, server-side to actually hold), and every skip is reported with a reason | ✅ implemented (`lib/importFiles.ts`, `POST /projects/import`) |
| **CRDT collaborative editing** — several people in one file at once (Yjs over a WS relay; server never merges) | ✅ implemented (`core/collab.py`, `y-monaco`) — proven by a 5-concurrent-editor test |
| **Version control** — content-addressed blobs, commits, branches, diffs, restore-with-rescue-branch | ✅ implemented (`services/vcs.py`) |
| **AI coding assistant** — explain / find bugs / write tests / document / refactor on your selection | ✅ implemented (`/projects/{id}/assist`, deliberately bypasses RAG) |
| **Browser code execution** — Python + JavaScript in an opaque-origin sandboxed frame; CPython on WASM, timeout-killed, zero server-side execution | ✅ implemented (`routes/runner.py`, `lib/runCode.ts`) |
| **Industry-adaptive workspaces** — the taskbar and starter content change with the workspace's field | ✅ implemented (`services/industries.py`, `os/Dock.tsx`) |
| **Row-Level Security backstop** — Postgres RLS under a NOLOGIN role, beneath the ORM filter and SQL guard | ✅ implemented (`core/database.py`) |
| MIT licensed | ✅ LICENSE |
| LoRA fine-tuning | 🔜 stretch (see docs/ROADMAP.md) |

## Testing

```bash
cd backend && pytest -q                       # 385 tests
cd backend && pytest -q -n 4 --dist loadfile  # ~4x faster (pytest-xdist)
```

Covers the auth flow, RBAC enforcement, JWT tamper resistance, chunking behaviour, SQL injection
guardrails, cross-tenant isolation, five people editing one file concurrently, and the code
sandbox's security headers — the last of these asserts that the sandbox is granted **no** `'self'`
in any CSP directive, because that single word is what stands between a colleague's code and your
session.

---

*Built as a production-style reference implementation: every "advanced" dependency (Qdrant, Postgres, Ollama, OCR, LangGraph) is isolated behind an interface with a working fallback, so the system degrades gracefully instead of breaking.*
