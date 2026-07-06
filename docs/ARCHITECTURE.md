# EAIOS Architecture

## 1. System overview

EAIOS is a three-tier platform with an AI middle layer. The design principle throughout is **interface + fallback**: every heavy dependency (Postgres, Qdrant, Ollama, OCR) sits behind a small abstraction with a zero-dependency implementation, so the platform always boots and each production component can be enabled independently.

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND · React 18 + TypeScript + Vite                     │
│ OS shell: Boot → Login → Desktop (MenuBar · Dock · Windows  │
│ · ⌘K Palette) hosting 8 window apps. Zustand state.         │
│ api.ts auto-detects backend; falls back to demo data.       │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST /api (JWT bearer)
┌───────────────────────────▼─────────────────────────────────┐
│ BACKEND · FastAPI                                           │
│ auth · users · documents · chat · agents · admin · analytics│
│ deps.py: get_db / get_current_user / require_role           │
├─────────────────────────────────────────────────────────────┤
│ ORCHESTRATOR (LangGraph-style state machine)                │
│ message → PlanningAgent.decompose → route() per subtask     │
│ → execute agents sequentially, chain outputs                │
│ → merge answers + citations + min(confidence)               │
├──────────────┬──────────────────────┬───────────────────────┤
│ RAG ENGINE   │ AGENTS (8)           │ LLM LAYER             │
│ parsers      │ document · sql       │ MockLLM (extractive)  │
│ chunking     │ research · email     │ OllamaLLM             │
│ embeddings   │ report · analytics   │ OpenAILLM             │
│ vectorstore  │ memory · planning    │ AnthropicLLM          │
│ retrieval    │ (AgentRun telemetry) │ safe_complete fallback│
├──────────────┴──────────┬───────────┴───────────────────────┤
│ PostgreSQL / SQLite     │ Qdrant / in-memory vector store   │
│ 8 tables (below)        │ cosine · payload {doc_id, page}   │
└─────────────────────────┴───────────────────────────────────┘
```

## 2. Hybrid multimodal RAG pipeline

Ingestion (background task per upload):

```
upload → parsers.parse_file (per-format extractors, section/page metadata)
       → chunking.chunk_blocks (sentence-aware, 900 chars, 150 overlap)
       → Chunk rows in SQL (source of truth for text)
       → embeddings.embed_texts (hash | ollama | sentence-transformers)
       → vectorstore.upsert (Qdrant or persistent in-memory)
       → Document.status = indexed
```

Retrieval (`rag/retrieval.py`) is genuinely hybrid:

1. **Dense**: query embedding → vector store top-k by cosine.
2. **Lexical**: BM25 (k1=1.5, b=0.75) implemented from scratch over the chunk corpus.
3. **Fusion**: Reciprocal Rank Fusion — `score(c) = Σ 1/(60 + rank)` across both lists.
4. Results carry `{title, section, page, normalized score}` → rendered as citation chips with relevance meters; answer confidence derives from mean retrieval score.

**Multimodal path**: PDF (pypdf), DOCX (heading-aware), PPTX (per slide), XLSX/CSV (row serialization), images (pytesseract when installed; graceful placeholder otherwise). Upgrade path: swap `parsers.py` internals for `unstructured`/Docling and add a VLM captioner behind the same `Block` interface — no downstream changes.

## 3. Multi-agent orchestration (graph runtime)

The orchestrator executes a compiled **StateGraph** (`agents/graph.py` — LangGraph API semantics implemented dependency-free: `add_node / add_edge / add_conditional_edges / compile / invoke`, dict-merge channel state). Swapping in the real LangGraph is a one-line import change.

```
START → planner ─▶ dispatch(conditional) ─▶ <agent node> ─┐
                        ▲                                 │
                        └─────────────────────────────────┘  (loop until queue empty)
                    dispatch ─▶ merge → END
```

- **Routing**: ordered regex intent table → memory / sql / research / email / report / analytics, default document (RAG). Transparent on purpose — explainable in a viva; swap for an LLM router without touching the API.
- **Planning**: `PlanningAgent.decompose` splits compound requests into subtasks queued through the graph; step N receives step N-1's output as reference context (typed agent-to-agent hand-off via shared state).
- **Resilience**: any graph failure falls back to a legacy sequential path with an identical result shape — chat never breaks.
- **Telemetry**: every node records a span in the active trace (§8) and emits `agent.step` events to the realtime hub (§9); `BaseAgent.run` still writes `AgentRun` rows.
- **Safety**: SQL Agent enforces single-statement, SELECT-only, keyword blocklist, comment ban, forced LIMIT; runs read-only against the session.

Workflows (Automations app) execute on the same agent runtime via `services/workflows.py`: a JSON DAG (trigger/agent/condition/notify nodes) walked breadth-first with `{{input}}` templating, per-node logs, tracing, and live event streaming. Upload-triggered workflows fire from the ingestion pipeline.

## 4. Database schema

| Table | Purpose | Key columns |
|---|---|---|
| users | auth + RBAC | email, hashed_password (PBKDF2), role, avatar_hue, last_login |
| documents | KB registry | filename, doc_type, status, chunk_count, owner_id, tags |
| chunks | RAG text | document_id, ord, text, section, page |
| conversations | chat threads | user_id, title, updated_at |
| messages | chat turns | role, content, agent, citations(JSON), confidence |
| agent_runs | observability | agent, status, duration_ms, input/output |
| memory_entries | long-term memory | user_id, kind(preference/fact/project), content, weight |
| audit_logs | compliance | user_id, action, detail, ip |
| entities | knowledge graph nodes | name, key(normalized, unique), etype, mentions |
| entity_edges | co-occurrence links | source_id, target_id, weight, doc_id |
| entity_mentions | evidence anchors | entity_id, chunk_id, document_id |
| workflows | automations | name, trigger, nodes(JSON), edges(JSON), enabled, run_count |
| workflow_runs | run history | workflow_id, status, log(JSON per node), duration_ms |

IDs are UUID hex strings; SQLite in dev (WAL + busy-timeout pragmas, load-test informed pool sizing), Postgres in compose/K8s (same SQLAlchemy 2.0 models).

## 5. Security model

- **Passwords**: PBKDF2-HMAC-SHA256, 100k iterations, random salt, constant-time compare.
- **Tokens**: HS256 JWT built on stdlib hmac (no third-party crypto), exp/iat claims, tamper-verified.
- **RBAC**: `require_role("admin")` dependency; roles admin/manager/employee; UI mirrors the matrix in Admin → Access.
- **SQL safety**: allowlist + blocklist + LIMIT injection (see §3).
- **Audit**: append-only log on login (success/fail with IP), uploads, deletions, role changes, model config views.
- **Rate limiting**: token buckets per user/IP (`core/ratelimit.py` middleware) — login 20/min, chat 60/min, upload 60/hr; 429 + Retry-After; in-memory by default, Redis-backed across replicas when `REDIS_URL` is set.
- **Prod checklist**: HTTPS via ingress + cert-manager (Helm values), SECRET_KEY rotation, CORS pinned per environment, nightly `pg_dump` CronJob with retention.

## 6. Frontend OS shell

- **Window manager**: pointer-event drag (clamped to viewport), 3-direction resize, minimize/maximize/close with animations, z-order focus model, per-app singleton windows.
- **State**: single Zustand store — phase machine (boot→login→desktop), window rects/z, palette, agent-busy orb, chat hand-off draft.
- **Command palette**: fuzzy filter over apps + actions, full keyboard nav, "Ask AI" routes text into the Chat app through the store.
- **Live/Demo duality**: `api.ts` pings `/api/health` (2s timeout); every feature has a mock twin with identical shapes, so the demo never dies on stage.
- **A11y**: focus-visible rings, aria-labels on icon buttons, `prefers-reduced-motion` kill-switch, 4.5:1 contrast on text tokens.

## 7. Delivered scale-up items (were "next steps", now shipped)

| Step | Implementation | Where |
|---|---|---|
| Graph orchestrator | StateGraph runtime, LangGraph semantics, legacy fallback | agents/graph.py, orchestrator.py |
| Real embeddings | `EMBEDDING_PROVIDER=auto` → Ollama nomic-embed when pulled, hash fallback | rag/embeddings.py |
| VLM captioning | any pulled Ollama vision model captions images at ingest | rag/parsers.py, llm/provider.py |
| Realtime collab | WS hub: presence, live agent feed, event replay | core/events.py, api/routes/ws.py |
| Knowledge graph | ingest-time NER → SQL graph; BFS relate; graph-augmented RAG | services/kgraph.py, Graph app |
| Workflow builder | custom node canvas → JSON DAG → agent runtime | services/workflows.py, Automations app |
| Observability | span traces per request; Traces app; optional OTel/Langfuse export | core/tracing.py, Traces app |
| Rate limiting | token buckets, Redis slot-in | core/ratelimit.py |
| K8s | Helm chart (HPA, Qdrant STS, TLS ingress, backup CronJob) + raw manifests | deploy/helm/eaios, deploy/k8s.yaml |
| CI/CD | pytest + builds + GHCR push on main + gated Helm deploy | .github/workflows/ci.yml |

## 8. Observability

`core/tracing.py` — contextvar-scoped traces with spans (`agent`, `llm`, `retrieval`, `graph`); ring buffer of 200 served at `/api/traces`; mirrored to OpenTelemetry (OTLP) and/or Langfuse when configured. Zero external services required — the Traces app renders waterfalls from the in-process buffer.

## 9. Realtime layer

`core/events.py` — single in-process hub; sync agent code publishes via `run_coroutine_threadsafe` onto the captured event loop; WS clients get presence + `agent.step`/`doc.status`/`workflow.*`/`chat.message` events; late joiners replay the last 20 from the ring buffer; `/api/events/recent` is the REST fallback. Redis pub/sub replaces `_broadcast` for multi-replica.

## 10. Load profile (measured)

`backend/tests/load/loadtest.py` (httpx/asyncio; locustfile.py also provided) against a single uvicorn worker, SQLite + mock LLM, sandboxed CPU:

- 60 users · 15s → **94 req/s, 0 errors**, p50 337ms · p95 1.9s
- 100 users · 20s → **98 req/s, 0 errors**, p50 754ms · p95 2.1s

The run exposed and fixed a real defect: default SQLAlchemy pool (5+10) exhausted under 60 concurrent chats → widened pool + SQLite WAL/busy-timeout pragmas. Postgres + HPA raises the ceiling further.

## 11. Remaining stretch

CRDT (Yjs) shared notes · LoRA fine-tuning from thumbs-up answers · LLM-based entity extraction (`kgraph.extract_entities` is the seam) · Neo4j graph backend. Each lands behind an existing interface — no rewrites, which is the point of the architecture.
