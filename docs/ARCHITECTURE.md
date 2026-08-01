# K-OS Architecture

## 1. System overview

K-OS is a three-tier platform with an AI middle layer. The design principle throughout is **interface + fallback**: every heavy dependency (Postgres, Qdrant, Ollama, OCR) sits behind a small abstraction with a zero-dependency implementation, so the platform always boots and each production component can be enabled independently.

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND · React 18 + TypeScript + Vite                     │
│ OS shell: Boot → Login → Desktop (MenuBar · Dock · Windows  │
│ · ⌘K Palette) hosting 19 window apps; the dock adapts to    │
│ the workspace's industry. Zustand state.                    │
│ api.ts auto-detects backend; falls back to demo data.       │
│ Code runs in a sandboxed opaque-origin frame, never server- │
│ side (§12).                                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST /api (JWT bearer) · WS (presence · CRDT)
┌───────────────────────────▼─────────────────────────────────┐
│ BACKEND · FastAPI                                           │
│ auth · users · documents · chat · agents · admin · analytics│
│ search · tasks · projects (code + VCS) · dashboards · …     │
│ deps.py: get_db / get_current_user / require_role           │
├─────────────────────────────────────────────────────────────┤
│ ORCHESTRATOR (LangGraph-style state machine)                │
│ message → PlanningAgent.decompose → route() per subtask     │
│ → execute agents sequentially, chain outputs                │
│ → merge answers + citations + min(confidence)               │
├──────────────┬──────────────────────┬───────────────────────┤
│ RAG ENGINE   │ AGENTS (9)           │ LLM LAYER             │
│ parsers      │ document · sql       │ MockLLM (extractive)  │
│ chunking     │ research · email     │ OllamaLLM             │
│ embeddings   │ report · analytics   │ OpenAILLM             │
│ vectorstore  │ memory · planning    │ AnthropicLLM          │
│ tables→SQL   │ coding               │ OpenRouter            │
│ retrieval    │ (AgentRun telemetry) │ safe_complete fallback│
├──────────────┴──────────┬───────────┴───────────────────────┤
│ PostgreSQL / SQLite     │ Qdrant / in-memory vector store   │
│ 27 tables · RLS backstop│ cosine · payload {doc_id, page}   │
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

- **Dynamic semantic routing** (`ROUTER_MODE=auto|llm|regex`): a single fast LLM call classifies the query against the agent catalog and returns strict JSON `{"tasks":[{"agent","task"}]}`; validated tasks **fan out in parallel** (thread pool, one DB session per branch, channel reducers merge the deltas) and converge at `merge`. Malformed JSON, a mock provider, or `regex` mode fall back to the transparent ordered regex intent table — deterministic and explainable in a viva.
- **Planning (fallback path)**: `PlanningAgent.decompose` splits compound requests into subtasks queued sequentially through the graph; step N receives step N-1's output as reference context (typed agent-to-agent hand-off via shared state).
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
| projects | code projects | name, description, language, owner_id |
| project_files | working tree | project_id, path, language, content, ydoc (CRDT state), updated_by |
| file_versions | per-file snapshots | file_id, content, author_name, note |
| blobs | content-addressed store | id = sha256(org_id ‖ content), content, size_bytes |
| commits | snapshot history | project_id, branch, message, author, parent_id, file_count |
| commit_files | commit → tree | commit_id, path, blob_id, language |

IDs are UUID hex strings; SQLite in dev (WAL + busy-timeout pragmas, load-test informed pool sizing), Postgres in compose/K8s (same SQLAlchemy 2.0 models).

Two schema lessons the code encodes, both learned from production failures:

- **`create_all` never alters an existing table.** New indexes, constraints and cascades on tables that
  already exist need explicit migration, which `core/database.py` performs on boot.
- **Postgres aborts the whole transaction on any failed statement.** A `try/except` around one DDL
  statement catches the exception but leaves the transaction poisoned, so every later repair fails too.
  Each repair therefore gets its own `engine.begin()`.

`ProjectFile → chunks`-style parent/child deletes carry cascades at *both* levels — ORM
`cascade="all, delete-orphan"` **and** DB `ondelete="CASCADE"` — because SQLite does not enforce foreign
keys by default, so an ORM-only cascade passes the test suite and fails on Postgres.

## 5. Security model

- **Passwords**: PBKDF2-HMAC-SHA256, 100k iterations, random salt, constant-time compare.
- **Tokens**: HS256 JWT built on stdlib hmac (no third-party crypto), exp/iat claims, tamper-verified.
- **RBAC**: `require_role("admin")` dependency; roles admin/manager/employee; UI mirrors the matrix in Admin → Access.
- **SQL safety**: allowlist + blocklist + LIMIT injection (see §3).
- **Tenant isolation, three layers deep**: an ORM `with_loader_criteria` filter scopes every read and
  stamps every write; the NL→SQL agent has a regex guard that rejects any statement it cannot prove
  stays in one workspace (a qualified `SELECT * FROM public.tasks` once slipped past a narrower
  version of it); and Postgres Row-Level Security under a `eaios_restricted` NOLOGIN role sits
  underneath both, so a bug in either upper layer still cannot return another tenant's rows.
- **Untrusted code execution**: user code runs in an iframe sandboxed to an opaque origin — no
  cookies, no storage, no parent DOM, CORS-blocked from this API — and inside a terminable Web
  Worker. The threat is not a malicious visitor but a *collaborator*: the Code app is shared, so the
  code you press Run on may have been typed by someone else. A same-origin Web Worker would have run
  it with your session. See §12.
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
| CRDT collaborative editing | Yjs over a WS relay; server never merges | core/collab.py, Code app |
| Code version control | content-addressed blobs, commits, branches, diffs | services/vcs.py |
| Sandboxed code execution | opaque-origin iframe → blob worker → Pyodide/JS | api/routes/runner.py |
| Row-Level Security | `eaios_restricted` NOLOGIN role beneath the ORM filter | core/database.py |
| Industry-adaptive workspaces | per-field app sets, agents, starter content | services/industries.py |

## 8. Observability

`core/tracing.py` — contextvar-scoped traces with spans (`agent`, `llm`, `retrieval`, `graph`); ring buffer of 200 served at `/api/traces`; mirrored to OpenTelemetry (OTLP) and/or Langfuse when configured. Zero external services required — the Traces app renders waterfalls from the in-process buffer.

## 9. Realtime layer

`core/events.py` — single in-process hub; sync agent code publishes via `run_coroutine_threadsafe` onto the captured event loop; WS clients get presence + `agent.step`/`doc.status`/`workflow.*`/`chat.message` events; late joiners replay the last 20 from the ring buffer; `/api/events/recent` is the REST fallback. Redis pub/sub replaces `_broadcast` for multi-replica.

## 10. Load profile (measured)

`backend/tests/load/loadtest.py` (httpx/asyncio; locustfile.py also provided) against a single uvicorn worker, SQLite + mock LLM, sandboxed CPU:

- 60 users · 15s → **94 req/s, 0 errors**, p50 337ms · p95 1.9s
- 100 users · 20s → **98 req/s, 0 errors**, p50 754ms · p95 2.1s

The run exposed and fixed a real defect: default SQLAlchemy pool (5+10) exhausted under 60 concurrent chats → widened pool + SQLite WAL/busy-timeout pragmas. Postgres + HPA raises the ceiling further.

## 11. Collaborative editing (Code app)

`core/collab.py` · `apps/CodeApp.tsx` · `services/vcs.py`

**The document is a CRDT, so the server does not have to be clever.** Each keystroke becomes a small
binary Yjs update. The server keeps one room per file, relays updates to the other editors and
persists the merged state on a 3-second debounce — it never parses or merges the document. Convergence
is a property of the data structure, not of the transport, so updates can arrive out of order, a
client can reconnect after a drop, and everyone still lands on identical text. Operational transform
would have required the server to understand and rewrite every edit; this does not.

The editor is Monaco, **bundled, not CDN-loaded** — the app's CSP allows `script-src 'self'`, so a CDN
loader would simply be blocked. It lands in its own lazy Vite chunk (~3.9 MB) that only downloads when
someone opens the Code app.

Version control borrows three ideas from git and deliberately omits a fourth:

- *Content addressing* — a file's contents are stored once under `sha256(org_id ‖ content)`. Salting
  with the workspace matters: a plain content hash is a global key, but blobs are tenant rows, so the
  session filter hides another workspace's blob, the lookup misses, and the insert then collides on
  that global key. Two workspaces committing an empty file would break each other's commits.
- *Commits are snapshots, not diffs* — a commit records the whole tree, so restoring is exact rather
  than a patch replay. Diffs are computed on demand.
- *A parent chain* — history is walkable; branching is two commits sharing a parent.
- **No merging.** Conflict resolution is a research-grade problem and a half-working merge is worse
  than none, so branches diverge, compare and restore. The UI states this rather than hiding it.

## 12. Code execution sandbox

`api/routes/runner.py` · `lib/runCode.ts`

No user code runs on the server. Running arbitrary code on a shared container is remote code execution
by another name, and no process trickery makes that safe on a free-tier box. Execution happens in the
browser, in three nested layers:

```
K-OS tab (authenticated, has the session)
 └── <iframe sandbox="allow-scripts">        ← opaque origin: no cookies, no storage,
      │                                        no parent DOM, CORS-blocked from /api
      └── Worker (blob:)                     ← terminable; survives `while True: pass`
           └── Pyodide (CPython → WASM) or JavaScript
```

`allow-same-origin` is omitted on purpose — granted *together with* `allow-scripts` it voids the
sandbox entirely, because the frame can then reach out and delete its own sandbox attribute. The
runner document is served with its own CSP that grants `'self'` in no directive except
`frame-ancestors`; in an opaque origin `'self'` matches nothing anyway, so granting it would only
mislead the next person to edit the policy. The sandbox may load one pinned CDN and nothing else — a
floating version would let an upstream release change what executes with no deploy here.

Two clocks, not one: downloading ~10 MB of CPython is not a runaway program, so a generous boot
timeout runs until the worker reports that the code itself has started, at which point the much
shorter execution limit takes over. Otherwise every cold Python run would be killed mid-download.

Verified in the browser against production: frame origin reports `"null"`; `document.cookie`,
`localStorage` and `parent.document` all throw; `fetch('/api/health')` fails; `while(true){}` is killed
on time while the tab stays responsive.

## 13. Remaining stretch

LoRA fine-tuning from thumbs-up answers · LLM-based entity extraction (`kgraph.extract_entities` is the seam) · Neo4j graph backend · merge support for code branches. Each lands behind an existing interface — no rewrites, which is the point of the architecture.
