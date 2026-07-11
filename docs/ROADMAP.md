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

## Deliverables checklist

Report + architecture diagrams (docs/) · demo video script: boot → login → ⌘K → RAG answer with citations → compound request planner demo → SQL Studio → admin audit → kill backend mid-demo to show demo-mode resilience (judges love this) · GitHub repo with CI badge · deployed URL.
