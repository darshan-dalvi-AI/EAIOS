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

## Observability

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /traces?limit= | ✓ | Recent traces (chat + workflow), span counts, durations |
| GET | /traces/{id} | ✓ | Full span waterfall: kind (agent/llm/retrieval/graph), offsets, attrs |
| GET | /events/recent | — | Last 50 realtime events (REST replay of the WS feed) |

## Realtime

| Protocol | Path | Description |
|---|---|---|
| WebSocket | /ws?token=<jwt> | Presence + live events: `presence`, `agent.step`, `chat.message`, `doc.status`, `workflow.run`, `workflow.notify`. Send `ping` for keep-alive |

## Misc

| Method | Path | Description |
|---|---|---|
| GET | /health | `{status, version, llm_provider}` — used by the frontend live/demo detector |

### Error shape
FastAPI standard: `{"detail": "message"}` with 401 (bad/expired token), 403 (role), 404, 409 (conflict), 415 (file type), 422 (validation), **429 (rate limited — includes `Retry-After` header)**.

### Rate limits (per user token, IP fallback)
login 20/min · register 10/min · chat 60/min · upload 60/hr · workflow-run 30/min · sql 60/min. Disable with `RATE_LIMIT_ENABLED=0`; set `REDIS_URL` for cross-replica enforcement.
