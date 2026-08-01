# EAIOS API Reference

Base URL: `/api` · Auth: `Authorization: Bearer <jwt>` (from login) · Interactive docs: `http://localhost:8000/docs`

## Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /auth/register | — | Create employee account `{email, full_name, password≥8}` |
| POST | /auth/login | — | `{email, password}` → `{token:{access_token}, user}` · audited with IP |
| GET | /auth/me | ✓ | Current user profile |

## Documents (Knowledge Base)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /documents/upload | ✓ | Multipart file → queued → background RAG ingestion. Types: pdf docx pptx xlsx csv txt md png jpg |
| GET | /documents | ✓ | List with status/chunk counts |
| GET | /documents/{id}/chunks | ✓ | Inspect indexed chunks (section, page) |
| POST | /documents/{id}/reindex | ✓ | Re-run the pipeline |
| DELETE | /documents/{id} | owner/admin | Removes rows + vectors + file |

## Chat & Agents

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /chat | ✓ | `{message, conversation_id?, agent?}` → orchestrated answer with `plan[]`, `retrieved[]` citations, confidence |
| GET | /chat/conversations | ✓ | User's threads |
| GET | /chat/conversations/{id}/messages | ✓ | Thread history |
| DELETE | /chat/conversations/{id} | ✓ | Delete thread |
| GET | /agents | ✓ | Registry: id, name, description, capabilities |
| GET | /agents/runs?limit= | ✓ | Recent AgentRun telemetry |
| POST | /agents/sql | ✓ | `{question}` → `{sql, explanation, columns, rows, warning}` (read-only guardrails) |
| GET | /agents/sql/schema | ✓ | Live schema explorer: platform tables + extracted `dt_*` document tables (`{table, rows, columns[], source?}`) |

Uploads with tabular content (docx/pptx tables incl. nested, xlsx sheets, csv, pdf/txt grids) are **materialized as real SQL tables** (`dt_<doc>_<n>`) at ingest; the SQL Agent sees them in its schema and can query them directly. Chat runs are **checkpointed per conversation** (`graph_checkpoints`): an interrupted run resumes from the saved node when the same message is retried (`GRAPH_CHECKPOINTS=false` to disable).

### NL-to-BI · Agent Studio · Connectors

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /dashboards/chart | ✓ | `{question}` → SQL agent runs it, spec inferred: `{type: bar\|line\|pie\|table, x, series[], data[], sql, rows}` |
| GET/POST/DELETE | /dashboards | ✓ | Pin / list / unpin saved charts (per user) |
| GET/POST/PUT/DELETE | /studio/agents | ✓ | Custom-agent CRUD (`{name, system_prompt, tools:[rag\|web], hue}`); edit/delete gated to owner or admin |
| POST | /studio/agents/{id}/run | ✓ | Test-run a custom agent → `{answer, confidence, citations}`. Custom agents are also invocable via `POST /chat {agent: <slug>}` |
| GET | /connectors | ✓ | Configured sources with sync status |
| POST | /connectors/sync | ✓ | `{provider: sample\|google_drive\|gmail, token?}` → fetches + ingests into the KB → `{ingested, ...}`. `sample` needs no token; Drive/Gmail need an OAuth access token |

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /agents/meeting | ✓ | `{transcript, title, save_to_knowledge}` → structured minutes (summary/decisions/action items); optional ingest into the KB |
| POST | /reports/export | ✓ | `{title, content(md), format: pdf\|docx\|md}` → downloadable file (dependency-free PDF writer / python-docx) |
| POST | /documents/{id}/analyze | ✓ | `{kind: resume\|contract\|invoice\|auto}` → scorecard `{verdict, score, highlights[], summary}` (LLM JSON or deterministic heuristic) |
| POST | /admin/compare | admin | `{prompt, models[2]}` → both answers with per-model latency (Model Arena) |

**Scheduled workflows:** `trigger=schedule` workflows fire automatically — interval comes from the trigger node's `data.every` (minutes, default 60); the app-level scheduler loop checks every `SCHEDULER_INTERVAL` seconds (`SCHEDULER_ENABLED=false` to disable).

## Admin (role: admin)

| Method | Path | Description |
|---|---|---|
| GET | /admin/stats | Counters + vector backend + LLM provider |
| GET | /admin/audit?limit= | Audit trail |
| GET | /admin/config | Model config, secrets masked |
| GET | /users | All users |
| PATCH | /users/{id} | `{role?, is_active?, full_name?}` |

## Analytics

| Method | Path | Description |
|---|---|---|
| GET | /analytics/usage | messages_daily (14d) · documents_by_type · runs_by_agent · avg latency |

## Knowledge Graph

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /graph?q=&limit= | ✓ | Entities + co-occurrence edges (built automatically at ingest) |
| GET | /graph/relate?a=&b= | ✓ | Connection path (BFS ≤3 hops), shared documents, evidence chunks |

**PII flagging:** entity types `person` / `email` / `phone` are sensitive. Any access through `/graph/relate`, the Document Agent's graph augmentation, or the MCP server writes a `pii.access` audit entry (`{source, entities[]}`) and publishes a `security.pii` realtime event.

## Workflows (Automations)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /workflows | ✓ | All workflows |
| POST | /workflows | ✓ | `{name, trigger: manual\|upload\|schedule, nodes[], edges[], enabled}` |
| PUT | /workflows/{id} | owner/admin | Update definition |
| DELETE | /workflows/{id} | owner/admin | Delete + runs |
| POST | /workflows/{id}/run | ✓ | `{input}` → run with per-node `log[]`, traced + streamed |
| GET | /workflows/{id}/runs | ✓ | Last 20 runs |

Node types: `trigger` · `agent {agent, prompt}` (`{{input}}` = upstream output) · `condition {contains}` · `notify {message}`.

## Code projects (Code app)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /projects | ✓ | Workspace's code projects with file counts |
| POST | /projects | ✓ | `{name, description?, language?}` → 201 |
| PATCH | /projects/{id} | ✓ | Rename / re-describe |
| DELETE | /projects/{id} | owner/admin | Cascades to files, versions and commits |
| GET | /projects/{id}/files | ✓ | File tree (path, language, size, last editor) |
| POST | /projects/{id}/files | ✓ | `{path, content?}` → 201; language inferred from the extension |
| GET | /projects/files/{file_id} | ✓ | File with `content` |
| PUT | /projects/files/{file_id} | ✓ | `{content, note?}` → saves and snapshots a version |
| DELETE | /projects/files/{file_id} | ✓ | Remove file + its versions |
| GET | /projects/files/{file_id}/versions | ✓ | Version history (author, note, size) |
| POST | /projects/files/{file_id}/restore/{version_id} | ✓ | Roll a file back |

### Version control

Git's model — content-addressed blobs, snapshot commits, a parent chain — stored in Postgres.
Blob ids are `sha256(org_id \0 content)`: salting with the workspace keeps deduplication inside a
tenant, so two workspaces committing the same boilerplate cannot collide on a shared primary key.
Merging is deliberately absent; branches diverge, compare and restore, and the UI says so.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /projects/{id}/status | ✓ | `git status`: `{branch, head, added[], modified[], removed[], clean}` |
| POST | /projects/{id}/commits | ✓ | `{message, branch?}` → 201, or 409 when nothing changed |
| GET | /projects/{id}/commits | ✓ | History (newest first, ≤100) |
| GET | /projects/{id}/commits/{commit_id} | ✓ | One commit + its diff against its parent |
| GET | /projects/{id}/diff | ✓ | Uncommitted changes against the branch tip |
| POST | /projects/{id}/checkout/{commit_id} | ✓ | Restore files to a commit. Uncommitted work is auto-committed to a `rescue-*` branch first, so restoring can never silently discard it |
| GET | /projects/{id}/branches | ✓ | Branches with commit counts |
| POST | /projects/{id}/branches | ✓ | `{name, from?}` → 201 |

### AI assistance

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /projects/assist/actions | ✓ | Available actions |
| POST | /projects/files/{file_id}/assist | ✓ | `{action: explain\|fix\|test\|document\|refactor, selection?}` → `{action, answer, degraded}` |

This endpoint deliberately **bypasses the Coding Agent's retrieval step.** Routed through RAG, "explain
this function" came back quoting a liability clause from a contract in the knowledge base — the
retriever cannot tell that a code question wants code context, not company documents.

### Execution sandbox

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /code/runner | — | HTML document embedded as a sandboxed iframe. Carries its own CSP |

Unauthenticated because it is a static shell holding no workspace data; everything it runs is posted
in by the parent frame, which *is* authenticated. It is framed with `sandbox="allow-scripts"` and
**without** `allow-same-origin`, giving it an opaque origin: no cookies, no storage, no parent DOM,
and CORS rejects any call back to this API. Its CSP grants `'self'` in no directive except
`frame-ancestors` — in an opaque origin `'self'` matches nothing anyway, so granting it would only
mislead whoever edits the policy next. Python (CPython/WebAssembly, pinned Pyodide) and JavaScript run
in a terminable Web Worker inside that frame; there is no cooperative way to stop `while True: pass`,
so `terminate()` on a timeout is the only mechanism that works. **No user code executes server-side.**

## Observability

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /traces?limit= | ✓ | Recent traces (chat + workflow), span counts, durations |
| GET | /traces/{id} | ✓ | Full span waterfall: kind (agent/llm/retrieval/graph), offsets, attrs |
| GET | /events/recent | — | Last 50 realtime events (REST replay of the WS feed) |

## Realtime

| Protocol | Path | Description |
|---|---|---|
| WebSocket | /ws?token=<jwt> | Presence + live events: `presence`, `agent.step`, `chat.message`, `doc.status` (incl. `tables`), `workflow.run`, `workflow.notify`, `workflow.approval`, `security.pii`. Send `ping` for keep-alive |
| WebSocket | /ws/collab/{file_id}?token=<jwt> | Collaborative editing relay for one file |

**Collaborative editing:** the document is a Yjs CRDT. The socket carries opaque binary updates that
the server relays to the other editors of that file and periodically persists — it never parses or
merges the document, because CRDT convergence is a property of the data structure, not of the
transport. Updates may therefore arrive in any order and every client still lands on identical text.
Peer cursors and names ride the same socket as awareness frames.

**WebRTC signaling (Video Call):** `rtc.*` frames sent over the same socket carry a `{to: <user_id>}` field and are relayed point-to-point to that user only (never broadcast, never buffered). Types: `rtc.ring` / `rtc.accept` / `rtc.decline` / `rtc.offer` / `rtc.answer` / `rtc.ice` / `rtc.caption` / `rtc.end`; the server replies `rtc.unavailable` to the caller if the target has no open socket. Media is peer-to-peer (STUN only) and never touches the server.

## Misc

| Method | Path | Description |
|---|---|---|
| GET | /health | `{status, version, llm_provider}` — used by the frontend live/demo detector |

### Error shape
FastAPI standard: `{"detail": "message"}` with 401 (bad/expired token), 403 (role), 404, 409 (conflict), 415 (file type), 422 (validation), **429 (rate limited — includes `Retry-After` header)**.

### Rate limits (per user token, IP fallback)
login 20/min · register 10/min · chat 60/min · upload 60/hr · workflow-run 30/min · sql 60/min. Disable with `RATE_LIMIT_ENABLED=0`; set `REDIS_URL` for cross-replica enforcement.
