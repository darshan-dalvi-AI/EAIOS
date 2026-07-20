# EAIOS — Viva Kit (deck outline · 5-minute demo script · Q&A prep)

## 1 · Ten-slide deck outline

1. **Title** — *EAIOS: The Enterprise AI Operating System.* B.E. capstone, Darshan Dalvi. Live at eaios.onrender.com — works on this phone too.
2. **Problem** — mid-size companies (50–500 people) drown in scattered documents, emails and spreadsheets. Enterprise AI tools (Glean, Copilot) are priced and built for giants.
3. **Solution** — a private company AI presented as a literal operating system in the browser: 18 apps over one hybrid-RAG, multi-agent backend. Grounded, cited, audited, resumable.
4. **Architecture** — React OS shell → FastAPI → StateGraph orchestrator → 9 specialist agents (+ user-built ones) → hybrid RAG (BM25 + vectors, RRF) + knowledge graph + table→SQL → any LLM via one OpenRouter key or fully offline (Ollama/mock).
5. **Data in** — uploads (PDF/DOCX/PPTX/XLSX/CSV/images), Gmail & Drive one-click OAuth connectors, website crawler. Tables become real SQL; entities become a knowledge graph; PII access is audit-flagged.
6. **Answers out** — cited chat with confidence scores, citation-jump to source, global search, NL→SQL Studio, NL→BI dashboards, exportable PDF/DOCX reports.
7. **Collaboration** — realtime presence, multi-party WebRTC video with live captions + auto minutes, minutes → kanban tasks automatically, visual workflow automations with human-in-the-loop approvals.
8. **Enterprise-grade** — JWT + RBAC + append-only audit, rate limiting, AI usage & cost metering per user/model, GDPR export/erase + retention purge, live RAG-quality eval (hit-rate@3, MRR), load-tested 100 users / 0 errors, Helm chart + CI/CD.
9. **Engineering highlights** — dependency-free StateGraph with DB checkpointing (interrupted runs resume), self-correcting SQL agent, graceful degradation everywhere (demo mode = zero keys), 65 backend tests + headless browser QA in CI.
10. **Close** — "Enterprise knowledge problems, not enterprise budgets." Roadmap: refresh-token auto-resync, answer-feedback → LoRA fine-tuning, multi-tenant workspaces.

## 2 · Five-minute demo script

*Before the viva: open eaios.onrender.com ~2 min early (free tier wakes up), log in as admin@eaios.dev / admin12345, keep your phone logged in too. If the network dies, EAIOS demo mode keeps every app working — mention it, it's a feature.*

- **0:00 — Boot + tour (30s).** Show boot screen → desktop. "Every 'app' here is a real window over one AI backend." Point at the first-run tour.
- **0:30 — Ask with citations (60s).** Chat: *"How many annual leave days do we get?"* Show the streamed answer, agent plan, confidence, then **click the citation chip** → Knowledge opens on the exact source. "It never answers without receipts."
- **1:30 — Data becomes SQL + BI (60s).** Dashboards: type *"revenue by region as a bar chart"* → chart renders; pin it. "A CSV inside a Word file became a real SQL table; the SQL agent wrote that query and repaired it if it failed."
- **2:30 — Connectors (40s).** Open Connectors: click **Connect with Google** (consent popup) or crawl a docs URL. "Real Gmail and Drive, one click — same RAG pipeline, same citations."
- **3:10 — Meeting → tasks (50s).** Meeting app: paste two sentences of 'transcript' → minutes appear → open **Tasks**: action items are already cards. Drag one to Done. "Call → minutes → tasks, fully automatic."
- **4:00 — Governance (40s).** Admin → AI usage (cost per user/model) → Audit log → Analytics (live RAG eval scores). "We don't just use AI — we measure and govern it."
- **4:40 — Phone finale (20s).** Hand over your phone showing the same desktop full-screen. "Same platform, 18 apps, in your pocket."

## 3 · Likely questions & strong answers

- **"Is the RAG actually hybrid?"** Yes — BM25 keyword index + vector index, fused with Reciprocal Rank Fusion; relational questions are augmented with knowledge-graph paths. The live eval card in Analytics reruns a fixed query set (hit-rate@3, MRR) against the current index.
- **"What if the LLM hallucinates?"** Answers must cite retrieved chunks; confidence is surfaced; citation-jump lets anyone verify the source in one click; the mock engine proves the pipeline works with zero model.
- **"Why build your own StateGraph instead of LangGraph?"** Same semantics (nodes, reducers, conditional fan-out, checkpointer) with zero dependency risk; swapping to the real library is a one-line import. The DB checkpointer means an interrupted run resumes from the saved node.
- **"How is this secure?"** PBKDF2 + HS256 JWT, RBAC on every route, SELECT-only SQL guardrails, SSRF blocklist on the crawler, PII access flagged to an append-only audit log, rate limiting, GDPR export/erase, retention purge.
- **"Does it scale?"** Load-tested at 100 concurrent users (98 req/s, p95 2.1 s, 0 errors) on one worker + SQLite; Postgres/Qdrant/Redis and a Helm chart with HPA are drop-in via env.
- **"What's the cost model?"** One OpenRouter key covers seven model families; the Admin metering tab shows requests/tokens/estimated cost per user and model — switch models live from Settings.
- **"What would you do next?"** Refresh-token auto-resync for connectors, answer feedback → LoRA fine-tuning on thumbs-up data, multi-tenant workspaces, CRDT shared notes.

## 4 · One-liner

> **EAIOS turns a company's scattered documents, mail and spreadsheets into a cited, governed, self-hosted AI operating system — enterprise knowledge problems, not enterprise budgets.**
