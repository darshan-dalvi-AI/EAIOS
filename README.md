# EAIOS — Enterprise AI Operating System

![CI](https://github.com/darshan-dalvi-AI/EAIOS/actions/workflows/ci.yml/badge.svg)

**A hybrid multimodal RAG, multi-agent AI platform for enterprise knowledge — presented as a literal operating system in the browser.**

Boot screen → login → desktop with a taskbar, draggable windows, and a Ctrl+K command palette. Eleven "apps" (AI Chat, Knowledge, Agents, **Graph**, **Automations**, **Traces**, SQL Studio, Analytics, Admin, Terminal, Settings) run as windows on top of a FastAPI + multi-agent + hybrid-RAG backend with realtime WebSocket presence.

> Final-year B.E. Computer Engineering capstone · React + TypeScript + FastAPI + Qdrant + PostgreSQL · runs fully offline with zero API keys

---

## Why it's different

Most "enterprise chatbot" projects are a chat box over an API call. EAIOS is:

- **An OS metaphor UI** — window manager, dock with magnification, boot sequence, command palette, faux shell. No enterprise tool ships like this; it demos unforgettably.
- **Genuinely grounded RAG** — hybrid retrieval (dense vectors + BM25, fused with Reciprocal Rank Fusion), citation chips with relevance meters, per-answer confidence scores.
- **A real multi-agent system** — a Planning Agent decomposes compound requests and routes subtasks across 8 agents (Document, SQL, Research, Email, Report, Analytics, Memory, Planning), each recorded in an observability table.
- **Zero-dependency dev mode** — SQLite + in-memory vector store + a deterministic extractive "mock LLM" mean the entire platform runs with no Docker, no GPU, no keys. Swap one env var to move to Postgres + Qdrant + Ollama/GPT/Claude.
- **Security done properly for a student project** — PBKDF2 password hashing, stdlib HS256 JWTs, RBAC guards, SELECT-only SQL guardrails, append-only audit log.
- **Graph-orchestrated agents with real observability** — the orchestrator is a StateGraph (LangGraph semantics, dependency-free); every chat/workflow run records a span waterfall you can open in the Traces app (OTel/Langfuse exporters optional).
- **A knowledge graph that builds itself** — entities + co-occurrence edges extracted at ingest, explored in a force-directed constellation (Graph app), and used to answer "how are X and Y related?" with paths + cited evidence.
- **Visual automations** — drag-and-drop workflow canvas (trigger → agents → conditions → notify) executed by the same agent runtime, with live-streamed runs; fires automatically on document upload.
- **Realtime presence** — WebSocket hub pushes who's online + live agent activity to every window.

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

**Logins** — `admin@eaios.dev / admin12345` (admin) · `maya@eaios.dev / demo12345` (manager) · `dev@eaios.dev / demo12345` (employee)

The frontend auto-detects the backend. If it's down, every app still works in **Demo mode** on realistic mock data — the login screen tells you which mode you're in.

## Architecture

```
React 18 + TS (OS shell: windows/dock/palette)
        │  REST /api
FastAPI ──► Orchestrator ──► Planning Agent ──► 8 specialist agents
        │                         │
        │                  Hybrid RAG engine
        │            (parse→chunk→embed→index)
        │                 │              │
   PostgreSQL/SQLite   Qdrant / in-mem   LLM layer
   (users, docs,       (vectors, RRF     (mock │ Ollama │
    chats, audit)       + BM25 fusion)    OpenAI │ Anthropic)
```

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API_REFERENCE.md](docs/API_REFERENCE.md) · Plan: [docs/ROADMAP.md](docs/ROADMAP.md)

## Repository layout

```
backend/app/
  core/        config · JWT + PBKDF2 security · database · events (WS hub) · tracing (spans)
  api/routes/  auth · users · documents · chat · agents · admin · analytics · graph · workflows · traces · ws
  rag/         parsers · chunking · embeddings · vectorstore · hybrid retrieval · pipeline
  agents/      base · registry · graph (StateGraph runtime) · orchestrator · 8 agent implementations
  services/    kgraph (entity extraction + graph queries) · workflows (DAG executor) · audit
  llm/         provider abstraction (mock/ollama/openai/anthropic)
  seed.py      demo users + documents through the real pipeline
backend/tests/ auth flow · RBAC · JWT · chunking · SQL guardrails · graph engine · KG · workflows · WS
frontend/src/
  os/          BootScreen · LoginScreen · Desktop · MenuBar · Dock · Window · CommandPalette
  apps/        Chat · Knowledge · Agents · Graph · Automations · Traces · SQLStudio · Analytics · Admin · Terminal · Settings
  lib/         api client (live/demo fallback) · ws realtime client · mock data layer
docs/          architecture · API reference · 16-week roadmap · demo script
```

## Feature checklist (spec coverage)

| Module | Status |
|---|---|
| JWT auth + RBAC + audit log | ✅ implemented |
| Hybrid multimodal RAG (PDF/DOCX/PPTX/XLSX/CSV/images) | ✅ implemented (OCR pluggable) |
| Multi-agent system (8 agents + planner) | ✅ implemented |
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
| CRDT shared notes, LoRA fine-tuning | 🔜 stretch (see docs/ROADMAP.md) |

## Testing

```bash
cd backend && pytest -q
```

Covers the auth flow, RBAC enforcement, JWT tamper resistance, chunking behavior, and SQL injection guardrails.

---

*Built as a production-style reference implementation: every "advanced" dependency (Qdrant, Postgres, Ollama, OCR, LangGraph) is isolated behind an interface with a working fallback, so the system degrades gracefully instead of breaking.*
