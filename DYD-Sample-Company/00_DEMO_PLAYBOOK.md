# K-OS Demo Playbook — DYD Technologies

**Read this first.** It tells you what to upload, what to click in every app, what
to ask, and **what the answer should be** — so nothing dead-ends in front of the
panel.

The data is one coherent company. That is the point. The contract says a Silver
tier pays 2% per SLA breach capped at 10%; the incident table says Vertex breached
10 of 14; the transcript says the team knew; the Python script computes ₹98,000.
Four different apps, four different data types, one answer that reconciles. That
is much harder to fake than a chatbot answering from one PDF, and it is the thing
worth showing.

---

## ⚠️ Do this first — otherwise the answers look like raw data

Production is currently running the **mock LLM**. `GET /api/health` reports
`"llm_provider":"mock"`. Retrieval works perfectly without a model — I verified
it, 93% confidence with six citations across a contract, a CSV and a transcript —
but with no model configured, K-OS **pastes the retrieved chunks back at you**
instead of writing an answer.

So instead of

> "Vertex breached 10 of 14 SLA targets (71%). Under the Silver tier that is 2%
> per breach, capped at 10% of the ₹9,80,000 monthly fee — **₹98,000** payable."

you get a wall of `client_id | client_name | industry | ...`. The retrieval is
right; the prose is missing. A panel will read that as the system not working.

**Fix — 3 minutes:**

1. Get a free OpenRouter key at <https://openrouter.ai/keys>.
2. Render → k-os → Environment → **+ Add Environment Variable**
   Key `OPENAI_API_KEY`, value your key. Save, rebuild, and deploy.
3. Confirm: `https://k-os.onrender.com/api/health` should stop saying `"mock"`.

`LLM_PROVIDER` is already `auto`, `OPENAI_BASE_URL` already points at OpenRouter,
and `OPENAI_MODEL` is already a free Llama 3.3 70B — so the key is the only thing
missing. **This is a real API key, unlike the Google client ID: do not paste it
into a chat, a screenshot, or the repo.** Type it straight into Render.

Test the same question afterwards and you should get prose with the ₹98,000 in it.

---

## 0. Setup (5 minutes, do this before the review)

1. Sign in at **https://k-os.onrender.com** → *Sign in* → your account.
   (Or *Try the live demo* if you want a throwaway workspace.)
2. Open **Knowledge** from the dock.
3. Drag in **everything except the `code/` folder** — all 7 `.md`, 6 `.csv`,
   2 `.txt`. Wait for each to show *Indexed*.
4. Watch the **Tables** count rise. The 6 CSVs become real SQL tables — that is
   the table→SQL pipeline running, and it is what makes the SQL, Analytics and
   Dashboards apps work.
5. Open **Code** and import the `code/` folder separately (it is source, not
   knowledge).

**Wake the server first.** Free tier sleeps after 15 minutes and takes ~50 seconds
to wake. Open the site once, a minute before you present.

---

## 1. AI Chat — the headline

**Steps:** Dock → *AI Chat* → leave Route on *Auto (planner)*.

| Ask | You should get |
|---|---|
| "What is our SLA breach position with Vertex Logistics, and what do we owe them?" | 10 of 14 breached (71%), Silver tier, 2% per breach capped at 10% → **₹98,000**. Cites the MSA *and* the incident data. |
| "Which single defect causes the most SLA breaches, and what is being done?" | The order-service memory leak, **5 breaches**, ticket NWR-1184, deferred 3 sprints, now first in the sprint from 28 July, owner Kabir Menon, production by 14 Aug. |
| "Are we at risk of losing any client contractually?" | Vertex — MSA §4 chronic-failure clause, 3 consecutive months at the cap allows termination for cause. One month in. |
| "Summarise the commercial position on the Meridian core banking project." | Fixed price ₹4.2cr, 92% spent, 2 milestones open, margin fell 28% → 9%, recovery depends on 2 unsigned change requests worth ₹31L. |

**Point at the citations.** Every answer carries the source document and section,
plus a confidence score. Click one — it opens the exact passage.

**The killer follow-up:** "Which of those did you get from a contract and which
from a spreadsheet?" It will separate them. That is retrieval across document
*types*, not just document search.

---

## 2. Knowledge — ingestion and grounding

**Steps:** Dock → *Knowledge*. Show the list, the chunk counts, the extracted tables.

- Click any document → the extracted text and its chunks.
- Click **Tables** → the SQL tables pulled out of the CSVs, with column types.
- Delete a document and re-ask a question that depended on it — the answer changes
  and the citation disappears. **This proves answers are grounded, not memorised.**

**Say this:** "Nothing here was in the model. Everything is retrieved at question
time from documents this company uploaded, and every claim is traceable."

---

## 3. Enterprise Search — retrieval without the LLM

**Steps:** Dock → *Search*.

| Search | Shows |
|---|---|
| `service credit` | MSA §3, the Vertex transcript, the SOWs — ranked, with snippets |
| `memory leak` | Runbook §4, both transcripts, incident rows |
| `break-glass` | Halcyon SOW access-control table |
| `notice period` | Handbook §4 |

This is BM25 + dense vectors fused with RRF. Useful contrast: **Search finds
documents, Chat answers questions.** Show both so the difference is obvious.

---

## 4. SQL Assistant — natural language over real tables

**Steps:** Dock → *SQL*. The schema explorer on the left lists the tables extracted
from your CSVs.

| Ask | Expected |
|---|---|
| "Which client has the worst SLA breach rate?" | Vertex Logistics, 10/14 = 71% |
| "Total unpaid invoice value by client, worst first" | Halcyon ₹73,75,000 top; total ₹1,70,25,000 |
| "Which projects are over budget?" | **P09** Vertex Warehouse Integrations, ₹56L spent vs ₹52L budget |
| "How many employees have more than 30 bench days?" | 11 |
| "Average utilisation by role" | Table, several roles under the 80% target |
| "Top 3 root causes of breached incidents" | Memory leak (5), then autoscaling / disk / gateway |

**Show the generated SQL** — it is displayed above the result. Two things to point
out: it is read-only, and every query is automatically scoped to your organisation.
Ask it to `DROP TABLE` and watch it refuse.

> **Verified, and a warning.** I ran this on the live site before writing it. With
> the mock engine, SQL Studio translates *every* question into the same generic
> query — I asked about incidents per client and got
> `SELECT doc_type, COUNT(*) FROM documents GROUP BY doc_type`. The guardrails and
> the schema explorer are genuinely working (it showed `read-only · LIMIT 50` and
> the full table list), but natural-language→SQL needs a real model. **This app is
> the strongest argument for setting the OpenRouter key before Wednesday** — it
> looks broken without one, and excellent with one.

---

## 5. Code — WebAssembly execution in the browser

**Steps:** Dock → *Code* → open `code/sla_credit_calculator.py` → **Run**.

It prints the credit table, flags Vertex as capped, and explains that 5 of the 10
breaches cost DYD nothing. **₹98,000 — the same number Chat gave you from the
contract.** Same answer, two completely different routes.

Then run:

- `utilisation_and_bench_cost.py` → 11 people, 562 bench days, **₹76,14,800** idle
  cost, and the bench concentrated in Java/Oracle while demand is Terraform/Databricks.
- `invoice_ageing.js` → ageing buckets, Halcyon at 43% of the book, ₹5,79,775 of
  contractual interest DYD never invoices.

**The security point, if a technical examiner asks:** this runs Python compiled to
WebAssembly inside a sandboxed iframe with an opaque origin. It has no cookies, no
access to the K-OS session, no network except the Pyodide CDN. Nothing executes on
the server — running untrusted code server-side on a shared container would be
remote code execution, and there is no safe way to do it there.

---

## 6. Agents — 9 specialists, not one prompt

**Steps:** Dock → *Agents*. You see the roster: document, SQL, analytics, coding,
report, research, email, memory, planning.

| Ask in Chat | Which agent runs |
|---|---|
| "Draft an email to Halcyon's CIO about the overdue invoices" | **email**, grounded in the real ₹73.75L figure |
| "Write a Python function to compute service credits with the cap" | **coding** |
| "Give me a board summary of delivery health this quarter" | **report** + **analytics** |
| "Compare our SLA position across all five clients and recommend actions" | **planning** fans out to several in parallel |

Watch the agent chips light up during a run. The planner routes; independent tasks
run in parallel; interrupted runs resume mid-graph from a checkpoint.

---

## 7. Analytics & 8. Dashboards

**Steps:** Dock → *Analytics*, then *Dashboards*.

Charts build off the extracted tables. Things visible immediately: margin by
project (P09 negative), incidents by client (Vertex dominant), utilisation
distribution (a long tail under target), receivables ageing.

**Ask Analytics:** "What is the biggest controllable drain on margin this year?"
→ the bench: 562 days, ~₹76 lakh.

---

## 9. Automations

**Steps:** Dock → *Automations*. The IT Services profile ships **Contract intake
review**, off by default.

Turn it on, upload `03_SOW_Halcyon_HIPAA_Cloud.md`, and it extracts obligations
automatically on ingest. Point at the on/off switch: automations are opt-in, so
nothing surprising happens to a client's documents without a decision.

## 10. Tasks

**Steps:** Dock → *Tasks*. The industry profile seeds a starter board.

Better demo: ask Chat *"List the open actions from the weekly delivery review with
owners and dates"* → it returns B1–B8 from the transcript. Then add one as a task.
**Unstructured meeting text becoming tracked work** is the story.

## 11. Graph

**Steps:** Dock → *Graph*. Clients, projects, people and documents as a network.
Vertex sits in a dense cluster of incidents; Meridian connects to the risk register.
Useful for "how do you know these things relate?"

## 12. Meeting Assistant

**Steps:** Dock → *Meeting* → paste `20_Transcript_Vertex_Escalation_Call.txt`.
It returns a summary, the decisions, and actions A1–A5 with owners and dates.

## 13. Studio · 14. Video · 15. Voice

- **Studio** — generate a client-facing summary or one-pager from the researched data.
- **Video** — WebRTC call, screen share; presence is live in the menu bar.
- **Voice** — click the mic in Chat and *ask a question out loud*. Speech in,
  spoken answer out. Try: "What do we owe Vertex Logistics?" It reliably gets a
  reaction from a panel.

## 16. Traces · 17. Terminal

- **Traces** — OpenTelemetry spans for the last question. Shows retrieval, rerank,
  agent hops and token counts. This is the answer to *"how do you know it's not
  hallucinating?"* — you can see what it retrieved.
- **Terminal** — safe read-only shell over workspace state.

## 18. Admin · 19. Settings · Connectors

- **Admin** — users, roles (admin / hr / manager / employee), audit log. Every
  destructive action is recorded. **Show the audit log** — it lands well with
  examiners.
- **Settings** — switch the LLM live (GPT, Claude, Gemini, Llama via one
  OpenRouter key, or local Ollama). Switch mid-demo to show it is not hardcoded.
- **Connectors** — Gmail / Drive sync. Sign-in with Google is live.

---

## The 4-minute version, if time is short

1. **Chat** — "What do we owe Vertex and why?" → cited answer, ₹98,000.
2. **SQL** — "Which client has the worst SLA breach rate?" → 71%, show the SQL.
3. **Code** — run `sla_credit_calculator.py` → same ₹98,000, computed.
4. **Traces** — show what was retrieved to produce answer 1.

One number, reached three independent ways, with the evidence trail visible.

**What I verified on the live site (2 Aug):** all 8 documents indexed to 56 chunks;
the Vertex question returned **93% confidence with six citations** spanning the
MSA §1, MSA §3, the extracted contract table, the clients CSV and the escalation
transcript — retrieval genuinely reaching across three different file types; and
`sla_credit_calculator.py` ran in the Code app in 6.0 seconds with correct output.
The two things that did *not* work are both the missing model key, not the
platform: chat prose and NL→SQL.

---

## Questions a panel will actually ask

**"Is this just ChatGPT with extra steps?"**
No. Ask it something outside the documents — it says it does not know rather than
inventing. Delete a document and the corresponding answer degrades. The model is
the reasoning layer; the answers come from retrieval, and every one is cited.

**"How do you stop one company seeing another's data?"**
Three independent layers: an ORM filter, a regex guard on generated SQL, and
PostgreSQL row-level security under a restricted role. Any one can fail and the
data stays isolated.

**"What happens if the AI provider goes down?"**
It degrades to a mock engine and says so, with a low confidence score, rather than
pretending. Providers are swappable in Settings.

**"Did you build this or assemble it?"**
Both, honestly. FastAPI, React, Postgres, Qdrant are standard. The hybrid
retrieval fusion, agent orchestration graph, tenant isolation, table→SQL
extraction, and the WebAssembly sandbox are the engineering.

**"What does it not do?"**
Worth having an honest answer ready: no fine-tuning on customer data, no
guaranteed factual accuracy beyond what is retrievable, and the free hosting tier
sleeps. Saying this unprompted reads as confidence, not weakness.
