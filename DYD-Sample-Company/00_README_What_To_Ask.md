# DYD Technologies — sample company pack

Eight documents for a fictional Mumbai IT-services company, **DYD Technologies Pvt. Ltd.**
Upload all eight into your workspace and every feature of K-OS has something real to work on.

Each file was chosen to exercise a specific capability. Nothing here is filler.

---

## Upload order (Knowledge → Upload, or drag them all in)

| # | File | What it proves works |
|---|---|---|
| 01 | `DYD_Client_SOW_Northwind.md` | Cited RAG · answers the in-scope/out-of-scope question |
| 02 | `DYD_Incident_Response_Runbook.md` | Multi-step procedural retrieval |
| 03 | `DYD_Master_Services_Agreement.md` | Contract Q&A · service-credit thresholds · **3 SQL tables** |
| 04 | `DYD_Client_Contracts.csv` | **Tables → SQL** · Dashboards · NL-to-BI charts |
| 05 | `DYD_Project_Delivery_Status.csv` | **Tables → SQL** · status reporting · risk queries |
| 06 | `DYD_Team_Directory.csv` | **PII audit flag** · knowledge graph entities |
| 07 | `DYD_Employee_Handbook.md` | HR Q&A · **2 SQL tables** (expense limits, notice periods) |
| 08 | `DYD_Weekly_Standup_Transcript.txt` | Meeting app → minutes → **Tasks kanban** |

Wait for every document to reach **indexed** before demoing. Ten SQL tables are created in total.

---

## What to ask, app by app

### AI Chat — grounded answers with citations

> **"What is in scope for the current client SOW, and what is explicitly excluded?"**
> Answers from doc 01. Seven in-scope items, seven exclusions. **Click the citation** — Knowledge
> opens at that section. This single click is your best proof of grounding.

> **"Summarise our incident response runbook for a database failover."**
> Answers from doc 02 — the seven steps in order.

> **"Which client contracts have service credits, and at what thresholds?"**
> Answers from doc 03 — 5% / 10% / 20% by tier and availability band.

> **"How many annual leave days do we get, and can I carry them forward?"**
> Answers from doc 07: 24 days, up to 10 carried forward.

> **"Why must I scale the API to zero before promoting a standby?"**
> A *reasoning* question, not a lookup. The runbook explains split-brain and the nine-hour
> reconciliation. Good one to show the answer isn't keyword matching.

### SQL Studio — natural language to SQL

> **"How many clients are in each region?"**
> **"Which clients are on the Platinum tier?"**
> **"Show contracts with annual value above 5000000"**
> **"Which projects are at high risk?"**

Point at the guardrails badge: SELECT-only, keyword blocklist, forced row limits.

### Dashboards — NL-to-BI

> **"Total annual contract value by region as a bar chart"**
> **"Client count by service tier as a pie chart"**
> **"Projects by status as a bar chart"**

Then pin one. Say: *"A CSV became a real SQL table at upload. That was a sentence, not a BI ticket."*

### Search — one query across everything

> Type **`Northwind`** — hits across documents, passages, extracted tables and entities at once.

### Graph — knowledge graph

Open it and look for **Darshan Dalvi**, **Rohit Kulkarni**, **Northwind Logistics**, **Kavita
Menon**. Then in Chat:

> **"How are Rohit Kulkarni and the Northwind project related?"**
> Returns a connection path plus cited evidence — something plain retrieval cannot do.

### Admin → Audit log — the PII demo

Doc 06 contains names, emails and phone numbers. After asking anything that touches those
entities, open **Admin → Audit** and show the `pii.access` entries.

> Say: *"The system classified those as personal data at ingest, and every agent that touched
> them is recorded. That is the difference between using AI and governing it."*

### Meeting → Tasks

Open **Meeting**, paste the contents of doc 08, generate minutes. Five action items come out
(escalate Delhivery credentials, impact note, Proseware change request, Woodgrove defects,
runbook update). Then open **Tasks** — they are already kanban cards. Drag one to Done.

### Automations

Build: `on upload → Document Agent "Summarise {{input}}" → Notify`. Save, then upload any
document. The workflow fires by itself.

### Traces

Open it straight after a chat question — the span waterfall shows planner, retrieval and LLM
call with per-step latency.

### Code

Unrelated to these documents — create a `main.py`, open the same file in a second browser
window, type in both, then press **Run**.

---

## The honest-degradation demo

Ask something with no answer in the corpus:

> **"What is our policy on cryptocurrency payments?"**

The system says the knowledge base contains nothing relevant — with a low confidence score —
rather than inventing a policy. That is the behaviour to point at, deliberately.

---

## A note on the data

Every company, client and person here is fictional. Client names are Microsoft's standard
sample-database names (Northwind, Contoso, Fabrikam, Adventure Works, Litware, Woodgrove),
which are conventionally used for demos precisely because they are recognisably not real.
Phone numbers and email addresses are invented and belong to no one.

Say so if a professor asks — using obviously fictional data for a demo of a *data isolation*
platform is the correct choice, not a shortcut.
