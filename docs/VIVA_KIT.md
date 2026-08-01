# EAIOS — Viva Kit (deck outline · 5-minute demo script · Q&A prep)

## 1 · Ten-slide deck outline

1. **Title** — *EAIOS: The Enterprise AI Operating System.* B.E. capstone, Darshan Dalvi. Live at eaios.onrender.com — works on this phone too.
2. **Problem** — mid-size companies (50–500 people) drown in scattered documents, emails and spreadsheets. Enterprise AI tools (Glean, Copilot) are priced and built for giants.
3. **Solution** — a private company AI presented as a literal operating system in the browser: 19 apps over one hybrid-RAG, multi-agent backend, and the dock reshapes itself to the workspace's industry. Grounded, cited, audited, resumable.
4. **Architecture** — React OS shell → FastAPI → StateGraph orchestrator → 9 specialist agents (+ user-built ones) → hybrid RAG (BM25 + vectors, RRF) + knowledge graph + table→SQL → any LLM via one OpenRouter key or fully offline (Ollama/mock).
5. **Data in** — uploads (PDF/DOCX/PPTX/XLSX/CSV/images), Gmail & Drive one-click OAuth connectors, website crawler. Tables become real SQL; entities become a knowledge graph; PII access is audit-flagged.
6. **Answers out** — cited chat with confidence scores, citation-jump to source, global search, NL→SQL Studio, NL→BI dashboards, exportable PDF/DOCX reports.
7. **Collaboration** — realtime presence, multi-party WebRTC video with live captions + auto minutes, minutes → kanban tasks automatically, visual workflow automations with human-in-the-loop approvals, and a **Code app where several people edit one file simultaneously** over a CRDT, with version control and an AI assistant.
8. **Enterprise-grade** — multi-tenant workspaces isolated at three layers (ORM filter → SQL guard → Postgres RLS), JWT + RBAC + append-only audit, rate limiting, AI usage & cost metering per user/model, GDPR export/erase + retention purge, live RAG-quality eval (hit-rate@3, MRR), load-tested 100 users / 0 errors, Helm chart + CI/CD.
9. **Engineering highlights** — dependency-free StateGraph with DB checkpointing (interrupted runs resume), self-correcting SQL agent, CRDT editing where the server never merges, code execution sandboxed to an opaque origin so it can never touch the server or your session, graceful degradation everywhere (demo mode = zero keys), **385 backend tests** + headless browser QA in CI.
10. **Close** — "Enterprise knowledge problems, not enterprise budgets." Roadmap: refresh-token auto-resync, answer-feedback → LoRA fine-tuning, merge support for code branches.

## 2 · Five-minute demo script

*Before the viva: open eaios.onrender.com ~2 min early (free tier wakes up), log in as admin@eaios.dev / admin12345, keep your phone logged in too. If the network dies, EAIOS demo mode keeps every app working — mention it, it's a feature.*

- **0:00 — Boot + tour (30s).** Show boot screen → desktop. "Every 'app' here is a real window over one AI backend." Point at the first-run tour.
- **0:30 — Ask with citations (60s).** Chat: *"How many annual leave days do we get?"* Show the streamed answer, agent plan, confidence, then **click the citation chip** → Knowledge opens on the exact source. "It never answers without receipts."
- **1:30 — Data becomes SQL + BI (60s).** Dashboards: type *"revenue by region as a bar chart"* → chart renders; pin it. "A CSV inside a Word file became a real SQL table; the SQL agent wrote that query and repaired it if it failed."
- **2:30 — Connectors (40s).** Open Connectors: click **Connect with Google** (consent popup) or crawl a docs URL. "Real Gmail and Drive, one click — same RAG pipeline, same citations."
- **3:10 — Meeting → tasks (50s).** Meeting app: paste two sentences of 'transcript' → minutes appear → open **Tasks**: action items are already cards. Drag one to Done. "Call → minutes → tasks, fully automatic."
- **4:00 — Governance (40s).** Admin → AI usage (cost per user/model) → Audit log → Analytics (live RAG eval scores). "We don't just use AI — we measure and govern it."
- **4:40 — Phone finale (20s).** Hand over your phone showing the same desktop full-screen. "Same platform, 19 apps, in your pocket."

*Optional 45s swap-in if the panel is technical — the Code app:* open a `.py` file, have a second
browser window open the same file, type in both and show the text converging live. Then press **Run**:
`print()` output and the value of the last expression appear in the console. Say the line that matters:
*"That ran in this browser tab, not on the server — in a sandbox with no cookies, no storage and no
access to the API, because in a shared editor the code you press Run on might have been typed by
someone else."*

## 3 · Likely questions & strong answers

- **"Is the RAG actually hybrid?"** Yes — BM25 keyword index + vector index, fused with Reciprocal Rank Fusion; relational questions are augmented with knowledge-graph paths. The live eval card in Analytics reruns a fixed query set (hit-rate@3, MRR) against the current index.
- **"What if the LLM hallucinates?"** Answers must cite retrieved chunks; confidence is surfaced; citation-jump lets anyone verify the source in one click; the mock engine proves the pipeline works with zero model.
- **"Why build your own StateGraph instead of LangGraph?"** Same semantics (nodes, reducers, conditional fan-out, checkpointer) with zero dependency risk; swapping to the real library is a one-line import. The DB checkpointer means an interrupted run resumes from the saved node.
- **"How is this secure?"** PBKDF2 + HS256 JWT, RBAC on every route, SELECT-only SQL guardrails, SSRF blocklist on the crawler, PII access flagged to an append-only audit log, rate limiting, GDPR export/erase, retention purge.
- **"Does it scale?"** Load-tested at 100 concurrent users (98 req/s, p95 2.1 s, 0 errors) on one worker + SQLite; Postgres/Qdrant/Redis and a Helm chart with HPA are drop-in via env.
- **"What's the cost model?"** One OpenRouter key covers seven model families; the Admin metering tab shows requests/tokens/estimated cost per user and model — switch models live from Settings.
- **"How does simultaneous editing work — doesn't the server have to merge?"** No, and that is the point. The text is a Yjs CRDT: each keystroke is a small binary update that can arrive in any order and still converge to identical text on every client. The server keeps one room per file, relays updates and persists the result on a debounce — it never parses or merges the document. Operational transform would have forced the server to understand and rewrite every edit; a CRDT makes convergence a property of the data structure instead. Proven by a test that drives five concurrent editors.
- **"You let users run arbitrary code — isn't that a huge hole?"** It would be on the server, which is exactly why nothing runs there: running untrusted code on a shared container is remote code execution by another name. Execution happens in the user's own browser, in an iframe sandboxed to an opaque origin — no cookies, no storage, no parent DOM, and CORS rejects any call back to the API — inside a Web Worker that can be terminated, because `while True: pass` has no cooperative exit. The threat model is not a malicious stranger, it is a *colleague*: the editor is shared, so a same-origin Web Worker would have run their code with your session. I verified all four escape attempts fail against the live deployment.
- **"Why Pyodide from a CDN rather than vendored?"** CPython on WebAssembly plus the stdlib is ~10 MB, and most sessions never open the Code app, so vendoring would tax every deploy. Loading it into an opaque origin means a compromised CDN gets code execution in a context with no session and no API access — the same thing it would get by hosting that code on its own site. The version is pinned, so an upstream release cannot change what executes without a deploy here.
- **"What would you do next?"** Refresh-token auto-resync for connectors, answer feedback → LoRA fine-tuning on thumbs-up data, merge support for code branches (deliberately omitted — a half-working merge is worse than none), and replacing the Code app's native `prompt()` dialogs with in-app inputs.

## 4 · One-liner

> **EAIOS turns a company's scattered documents, mail and spreadsheets into a cited, governed, self-hosted AI operating system — enterprise knowledge problems, not enterprise budgets.**
