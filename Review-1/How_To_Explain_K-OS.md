# How to explain K-OS — every feature, with a working example

Each example below uses content that is **actually seeded in the demo**, so you can click it
live and it will work. Live at eaios.onrender.com.

---

## The one-sentence version

> "K-OS is a Knowledge Operating System. A company uploads its documents, and every person in
> that company can ask questions in plain English and get answers **with citations** — and one
> company's data can never appear in another company's answers, because the database itself
> enforces that, not the code."

If you only get to say one thing, say that. Everything else is detail.

---

## The 30-second version (use this to open)

> "Companies are adopting AI faster than they can operationalise it — 78% use it somewhere,
> about 6% have scaled it. The blocker isn't the model. It's three things: answers you can't
> verify, knowledge scattered across ten tools, and no real guarantee that a shared platform
> keeps one client's data away from another's.
>
> K-OS is one platform that solves all three, presented as a desktop operating system in the
> browser — nineteen apps over one AI backend."

---

# PART 1 — The four things that make it different

Explain these first. The app tour means nothing without them.

### 1. Every answer carries its receipts

Most AI tools give you a paragraph. K-OS gives you a paragraph, **the document it came from,
the section, and a confidence score.** Click the citation and the source opens at that spot.

> **Say this:** "An answer you can't check is an answer you can't act on. In an enterprise,
> that's the whole problem — so an answer without a citation is treated as a defect here,
> not a style choice."

### 2. Isolation is enforced by the database, not by the code

Three independent layers. Even if a programmer writes a buggy query, the database refuses to
return another company's rows.

> **Say this:** "Most platforms say 'we isolate tenants' and mean 'our code remembers to add
> a WHERE clause'. We tested that assumption and it failed — so we moved the guarantee into
> PostgreSQL itself." *(Full story in Part 3 — it's your strongest material.)*

### 3. It degrades honestly

Turn off the AI model entirely and nothing crashes. You get the real source excerpts and a
clear notice that generation is unavailable.

> **Say this:** "It never invents an answer to hide a failure."

### 4. It's an operating system, not a chatbot

Windows, a taskbar, a command palette. And the taskbar **changes by industry** — a consultancy
gets the Code app; a clinic gets the knowledge graph.

---

# PART 2 — The 19 apps, each with a working example

### Core — the ones to actually demo

**1. AI Chat** — *multi-agent enterprise assistant*
> **Try:** "How many annual leave days do we get?"
> **You get:** "24 days of paid annual leave per year, credited monthly. Up to 10 unused days
> carry forward" — with a chip reading `HR Leave Policy · §Annual` and `confidence 91%`.
> **Point at:** the agent chip showing which specialist answered, then **click the citation**
> so Knowledge opens on that exact section.

**2. Search** — *one query across everything*
> **Try:** `atlas`
> **You get:** matches from documents, passages, extracted tables, entities and past chats —
> in one result list.
> **Say:** "One box instead of opening four tools."

**3. Knowledge** — *documents & the RAG pipeline*
> **Try:** upload any PDF or spreadsheet and watch the status go queued → processing → indexed.
> **Then:** open the document and show the **chunks** — the actual text pieces the AI retrieves.
> **Say:** "This is where you see it isn't magic. The document is parsed, split, embedded and
> indexed twice — once for keywords, once for meaning."

**4. Agents** — *the fleet and live activity*
> **Show:** nine specialist agents — Planning, Document, SQL, Research, Email, Report,
> Analytics, Memory, Coding.
> **Say:** "A Planning Agent reads the request and decides who handles it. Independent parts
> run in parallel."

**5. SQL Studio** — *natural language to database*
> **Try:** "documents by type"
> **You get:** generated SQL, the result table, and a guardrails badge.
> **Say:** "SELECT-only, keyword blocklist, forced row limits. Natural language never gets
> write access to the database."

**6. Dashboards** — *NL-to-BI*
> **Try:** "revenue by region as a bar chart"
> **You get:** a rendered chart you can pin.
> **Say:** "That was a sentence, not a BI ticket. A table inside an uploaded Word file became
> a real SQL table, and the agent wrote the query against it."

**7. Graph** — *knowledge graph explorer*
> **Try:** drag a node, click one, walk its connections. Then in Chat ask
> "How are annual leave and sick leave related?"
> **Say:** "Entities and relationships are extracted at upload time. This answers 'how are X
> and Y connected' with a path plus cited evidence — which plain retrieval cannot do."

**8. Code** — *collaborative editing, live* ← **your showpiece**
> **Try:** open `main.py`, put a second browser window on the same file, type in both at once.
> **You get:** both windows converge to identical text, live.
> **Then press Run:** `print("hi")` then `import numpy as np; print(np.arange(5).sum())`
> **Say the line that lands:** *"That ran in this browser tab, not on the server — in a sandbox
> with no cookies, no storage and no access to the API. That matters because this editor is
> shared: the code you press Run on might have been typed by a colleague."*
> **Finish:** run `while True: pass` — killed on a timer, tab stays responsive. Then show
> **Git** → commit, branch, diff.

**9. Meeting** — *record → transcript → minutes*
> **Try:** paste two sentences of "transcript" → minutes appear (summary, decisions, actions).
> **Then open Tasks:** the action items are already kanban cards.
> **Say:** "Call → minutes → tasks, fully automatic."

**10. Tasks** — *kanban, auto-fed from meetings*
> **Try:** drag a card to Done.

**11. Automations** — *visual workflow builder*
> **Try:** build `on upload → Document Agent "Summarise {{input}}" → Notify`. Save. Upload a
> file in Knowledge.
> **You get:** the workflow fires by itself.
> **Say:** "Same agent runtime as chat, driven by a drag-and-drop DAG."

**12. Traces** — *observability*
> **Try:** open it right after a chat question.
> **You get:** a span waterfall — planner, retrieval, LLM call — each with latency.
> **Say:** "Langfuse-style observability with zero external services. Point one env var at an
> OTLP endpoint and these mirror to Grafana."

### Supporting apps

**13. Analytics** — usage KPIs, adoption trends, agent workloads, plus a **live RAG quality
score** (hit-rate@3 and MRR re-run against the current index).

**14. Agent Studio** — build a custom agent with no code: a name, a system prompt, and tool
toggles. It appears in Chat's route picker immediately.

**15. Connectors** — pull Gmail and Google Drive into the same pipeline as uploads. Also a
website crawler. *Sample workspace needs zero setup.*

**16. Video Call** — WebRTC multi-party calls with live captions, virtual backgrounds, screen
share, and minutes generated on hang-up.

**17. Admin** — users and roles, the append-only audit log, live model switching, and **AI cost
metering** per user and model. Also workspace suspend/delete for the platform owner.

**18. Terminal** — a faux shell. Fun in a demo; run `neofetch`.

**19. Settings** — switch AI model live, theme, install the app, replay the tour.

---

# PART 3 — The story that wins the review

**Do not skip this. It is the single most valuable thing you have.**

> "Our platform serves many companies from one deployment. So we had to guarantee that one
> company's data never reaches another. We built two layers to do that — a filter on every
> query, and a guard that rewrites any SQL the AI writes.
>
> Then we tested it properly. And it failed.
>
> A query written as `SELECT * FROM public.tasks` — just the schema name in front of the table —
> slipped past our guard and returned **every company's records** on the deployment, including
> user identities.
>
> We reproduced it with two live tenants, fixed it, and wrote regression tests. But then we did
> the thing that matters: we added a **third layer inside PostgreSQL itself** — Row-Level
> Security under a restricted role. Now a query with no tenant filter at all returns only your
> own rows, because the database will not show the others to that role.
>
> The security literature argues *from principle* that application-layer isolation isn't
> enough. We didn't have to take that on faith — we watched our own guard fail, and moved the
> guarantee into the database."

**Why this wins:** most student projects claim security. You have evidence — including evidence
of your own code failing, which you found, fixed, and designed around. That is what engineering
maturity looks like to an examiner.

---

# PART 4 — Questions you will be asked

**"Is the RAG actually hybrid?"**
> Yes — a BM25 keyword index and a vector index, fused with Reciprocal Rank Fusion. And there's
> a reason for both: dense retrieval matches *meaning*, which is exactly wrong for an invoice
> number or "Section 7.3(b)". Those aren't semantically similar to anything — they must be
> matched literally. The two fail in opposite ways, so we use both.

**"What if the AI hallucinates?"**
> Every answer must cite retrieved chunks, confidence is shown, and citation-jump lets anyone
> verify in one click. Ask an empty workspace to summarise contracts and it says the knowledge
> base has nothing — it does not invent.

**"Why build your own orchestrator instead of LangGraph?"**
> Same semantics — nodes, conditional fan-out, a checkpointer — with zero dependency risk.
> Swapping to the real library is a one-line import. And the DB checkpointer means an
> interrupted run resumes from the saved node instead of starting over.

**"You let users run arbitrary code — isn't that a hole?"**
> It would be on the server, which is exactly why nothing runs there. It runs in the user's own
> browser, in a frame with an opaque origin — no cookies, no storage, CORS-blocked from our API
> — inside a worker that can be terminated. The threat isn't a stranger, it's a *colleague*:
> the editor is shared, so a same-origin worker would have run their code with your session.

**"Does it scale?"**
> Load-tested at 100 concurrent users: 98 req/s, p95 2.1s, zero errors on a single worker with
> SQLite. That test found a real defect — the connection pool exhausted at ~60 users — which we
> fixed. Postgres, Redis and a Helm chart with autoscaling are drop-in via env vars.

**"What's the business model?"**
> One OpenRouter key covers seven model families. Admin shows requests, tokens and estimated
> cost per user and per model. Self-hosted, so no per-seat licensing.

**"What would you do next?"**
> Benchmark retrieval against a labelled corpus, per-row isolation for extracted tables, formal
> verification of the SQL guard, and merge support for code branches — deliberately left out,
> because a half-working merge is worse than none.

---

# PART 5 — The safety net

If the network dies mid-demo: **kill the backend on purpose and keep going.** Every app keeps
working on mock data, and the login screen tells you which mode you're in.

> **Say:** "This is demo mode. The entire interface survives on mock data — this platform
> cannot die on stage."

Examiners remember that more than any feature.

---

## Numbers to know cold

| | |
|---|---|
| Apps · agents · REST endpoints · tables | 19 · 9 · 104 · 27 |
| Backend / frontend lines | ~14,500 / ~11,600 |
| Automated tests passing | **422** |
| Structured audit | 10 passes, 24 findings, all fixed |
| Load test | 100 users, 98 req/s, p95 2.1s, 0 errors |
| N+1 fix | 202 queries → 2 |
| Bundle reduction | 861 KB → 302 KB |
