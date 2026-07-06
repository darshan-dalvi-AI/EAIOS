# EAIOS Demonstration Video Script (~6 minutes)

**Setup before recording**: `ollama pull llama3.1 && ollama pull nomic-embed-text` · backend running (`uvicorn app.main:app`) · `python -m app.seed` done · frontend `npm run dev` · browser at localhost:5173, 1080p, dark room vibes.

1. **Cold open (0:00–0:30)** — Refresh the page. Let the boot sequence play silently, then say: *"This is EAIOS — an Enterprise AI Operating System. Not a chatbot with a dashboard — an actual OS metaphor: windows, a dock, a command palette — running a hybrid-RAG, multi-agent AI platform underneath."*

2. **Login + live mode (0:30–1:00)** — Point at the green "Live backend connected" chip. Log in as Maya. Mention JWT + role-based access.

3. **The money demo: grounded RAG (1:00–2:15)** — Ask: *"How many annual leave days do we get, and can I carry them forward?"* While it streams: *"Watch the planner route this to the Document Agent."* Then click a citation chip: *"Every answer carries its sources with relevance scores and a confidence figure — this is retrieval-augmented, not hallucinated."* Press the mic button and ask the next question by voice.

4. **Multi-agent chaining (2:15–3:00)** — Ask: *"Summarize Q3 revenue and then draft an email to the CFO about it."* Point at the plan chips (planning → document → email): *"One request, decomposed into two agent steps, with context handed from one to the next."*

5. **Knowledge + vision (3:00–3:45)** — Open Knowledge from the dock. Upload a scanned chart/invoice image. *"The ingestion pipeline runs layout parsing, OCR, and — because a local vision model is pulled — AI captioning. The chart's contents become searchable text."* Show the chunks in the detail drawer.

6. **SQL Studio (3:45–4:20)** — Ask *"documents by type"*. Show generated SQL + guardrails pill: *"SELECT-only, keyword blocklist, forced row limits — natural language never gets write access."*

7. **Window manager flex (4:20–4:50)** — Open Agents, Analytics, Terminal. Drag windows around, Ctrl+K → type a question → Enter. Run `neofetch` in Terminal for the crowd.

8. **Admin + kill shot (4:50–5:40)** — As admin: audit log (*"every login, upload, and role change is recorded"*), model config (*"swap mock → Ollama → GPT with one env var — it auto-detects"*). **Then kill the backend process live.** Refresh: *"Demo mode. The entire UI survives on mock data — this platform cannot die on stage."*

9. **Close (5:40–6:00)** — Architecture slide (docs/ARCHITECTURE.md diagram): React OS shell → FastAPI → agent orchestrator → hybrid RAG → Qdrant/Postgres → pluggable LLMs → Docker/K8s. *"Built to production patterns, designed to grow — the graph orchestrator, realtime layer, and Kubernetes manifests are already in the repo."*

---

## Extended cut (+3 min) — Phase 3–5 features

10. **Realtime presence (6:00–6:30)** — Open a second browser (incognito), log in as dev@eaios.dev. Point at the menu bar: *"Two avatars — presence over WebSockets."* Ask a question in browser A; switch to browser B's Agents app: *"The agent feed streams live to every connected user — no polling, no mocks."*

11. **Knowledge Graph (6:30–7:15)** — Open **Graph** from the taskbar. *"At ingest, EAIOS extracts entities and co-occurrence relationships — the knowledge base becomes a constellation you can explore."* Drag a node, click one, walk its connections. Then in Chat ask: *"How are annual leave and sick leave related?"* — *"Graph-augmented retrieval: connection path plus cited passages."*

12. **Automations (7:15–8:15)** — Open **Automations**. Build live: trigger (on upload) → Document Agent "Summarize {{input}}" → Notify. Save. Upload any file in Knowledge → jump to Agents: *"The workflow fired on its own — visual automation running on the same agent runtime as chat."* Run the Morning KPI brief manually and show the per-node log.

13. **Traces (8:15–9:00)** — Open **Traces**, click the last chat request. *"Every request is traced — planner, retrieval, LLM calls, each with latency and attributes, Langfuse-style but with zero external services. Point one env var at an OTLP endpoint and these mirror to Grafana."* Click a span to show attrs. *"That's observability judges can't argue with."*
