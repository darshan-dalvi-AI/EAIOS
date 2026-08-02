# K-OS — Review-1 Deck (12 slides): content + prompt to paste into Claude

**How to use:** copy **PART A** (the prompt) and **PART B** (the content) into one Claude message.

**Slide order:** Title → Problem Statement → **Primary Research (2 empty placeholders)** →
Secondary Research → Literature Review → Research Gap → Abstract & Objectives →
Architecture → Key Finding → Evaluation → Conclusion.

All figures are **verified against the live system on 1 Aug 2026** and supersede the older
numbers in the Review-1 .docx files (which say 354 tests, 18 apps, 21 tables, 80 endpoints).
Update those documents to match, or the deck and the report will contradict each other.

---

# PART A — THE PROMPT (paste this first)

> Build me a **12-slide** presentation deck for a final-year B.E. Computer Engineering major
> project first internal review. Audience: an academic panel of 2–3 faculty examiners.
> Duration: 12–15 minutes of speaking. Tone: technical, evidence-led, confident but not
> boastful — this is an engineering review, not a sales pitch.
>
> **Visual direction:** dark technical theme, deep navy/near-black background (#0a1018),
> cyan-to-violet accent gradient (#22d3ee → #8b5cf6). One clear idea per slide, generous
> whitespace, large numbers as visual anchors wherever a statistic appears. Monospace for
> anything code-like. No stock photography, no clip art, no emoji.
>
> **Rules — follow these strictly:**
> - Exactly 12 slides, in the order given. Do not add, merge or reorder them.
> - Every statistic must carry its source in small text beneath it.
> - **Do NOT invent any numbers, citations or results.** Use only what I give you. If
>   something looks missing, leave a visible placeholder rather than filling the gap.
> - **Slides 3 and 4 must be EMPTY placeholder slides** — heading only, plus a grey note
>   reading "Data collection in progress — survey closes [DATE]". I am collecting that data
>   from a Google Form and will fill those slides myself. Do not invent survey results,
>   sample sizes, percentages or charts for them.
> - Slide 10 is the most important slide in the deck. Give it the strongest visual treatment.
> - Put the 10 references on slide 12 in a small two-column block beneath the conclusion.
> - Include brief speaker notes under every slide.
>
> The content follows.

---

# PART B — THE CONTENT (paste this after the prompt)

## SLIDE 1 — Title

**K-OS: A Knowledge Operating System for the Enterprise**

Sub: A Multi-Tenant Platform with Hybrid Retrieval-Augmented Generation, Multi-Agent
Orchestration and Database-Enforced Tenant Isolation

- Major Project — First Internal Review · 5 August 2026
- Darshan Dalvi · [Teammate Name 2] · [Teammate Name 3]
- Guide: [Guide Name] · Coordinator: Mrs. Sharayu Patil · HOD: Mrs. C. M. Pandit
- Department of Computer Engineering, Vishwaniketan iMEET
- Affiliated to University of Mumbai · Approved by AICTE
- Live at: eaios.onrender.com

---

## SLIDE 2 — Problem Statement

### **78% adopt AI. ~6% actually scale it.**

- 78% of organisations use AI in at least one business function
- ~33% have scaled it across the organisation
- ~6% report enterprise-wide deployment

*Source: McKinsey & Company, "The State of AI: Global Survey," QuantumBlack, 2025.
n = 1,993 respondents, 105 nations, fielded 25 June – 29 July 2025.*

**The gap is not model capability. It is the surrounding system.** Three problems recur:

1. **Grounding** — a general model knows nothing of internal documents; asked anyway, it
   produces fluent text that cannot be verified.
2. **Fragmentation** — knowledge is scattered across mailboxes, drives and spreadsheets.
   No single interface answers a question spanning them.
3. **Isolation** — a platform serving several client organisations must guarantee one
   client's material never appears in another's results. This is routinely *asserted in
   application code* and rarely *enforced by the data layer*.

---

## SLIDE 3 — Primary Research: Method

### ⚠️ EMPTY PLACEHOLDER SLIDE

Heading only, plus a grey centred note:
**"Data collection in progress — survey closes [DATE]"**

*Do not generate content for this slide. I will fill in the instrument design, sampling
method and sample size once the Google Form closes.*

---

## SLIDE 4 — Primary Research: Findings

### ⚠️ EMPTY PLACEHOLDER SLIDE

Heading only, plus a grey centred note:
**"Data collection in progress — survey closes [DATE]"**

*Do not generate charts, percentages or findings for this slide. I will fill it from the
survey responses.*

---

## SLIDE 5 — Secondary Research

**Method — three classes of existing evidence:**

- **Peer-reviewed literature** — NeurIPS, EMNLP, ICLR, ACM Computing Surveys
- **Industry survey data** — McKinsey State of AI (n = 1,993, 105 nations)
- **Security guidance** — OWASP Top 10 for LLM Applications, 2025 edition

Ten primary sources. All independently retrievable and cited in full.

**What the market evidence shows:** the central finding is a *gap*, not a shortage.
Three-quarters of organisations use AI; roughly one in sixteen has scaled it. The difference
between those two numbers is the space this project occupies — the missing element is not a
better model but the surrounding system of ingestion, grounding, isolation, governance and
interface.

---

## SLIDE 6 — Literature Review: ten primary sources

| Area | Source | What it establishes |
|---|---|---|
| RAG foundations | Lewis et al., NeurIPS 2020 | Knowledge need not live in model weights — retrieve at inference, so it updates without retraining and answers are attributable |
| RAG taxonomy | Gao et al., 2023 | Naive / Advanced / Modular RAG; retrieval, generation, augmentation are separable |
| Dense retrieval | Karpukhin et al., EMNLP 2020 | Dense dual-encoder beats BM25 by **9–19% absolute** (top-20 accuracy) |
| Hallucination | Ji et al., ACM Comput. Surv. 2023 | *Intrinsic* contradicts the source; *extrinsic* cannot be verified against it |
| Agents | Yao et al., ICLR 2023 | ReAct — interleaving reasoning with action improves interpretability and trust |
| Text-to-SQL | Yu et al., EMNLP 2018 | Spider: 10,181 questions, 200 databases, 138 domains. Best system: **9.7% exact-match** |
| Graph retrieval | Edge et al., Microsoft 2024 | Conventional RAG fails on corpus-level questions — those are summarisation, not retrieval |
| Security | OWASP LLM Top 10, 2025 | Prompt injection **#1 for a second consecutive edition**; excessive agency added |
| Multi-tenancy | AWS Database Blog | Shared-schema is cheapest but weakest; RLS recommended as a database-level second defence |

---

## SLIDE 7 — Research Gap

**The literature solves each problem in isolation. No reviewed source combines them.**

1. **Multi-tenant RAG is largely unstudied.** Retrieval research assumes one corpus. It does
   not address the case where retrieving the wrong document is a **breach**, not a poor result.
2. **Text-to-SQL security is under-examined.** The literature optimises benchmark accuracy,
   not the safety of executing generated SQL against a live shared database.
3. **Multi-tenancy guidance predates LLM-composed queries.** Established patterns assume
   queries written by programmers and reviewed by humans — not composed at runtime by a model.
4. **No integrated open system was found** unifying hybrid RAG, agents, NL-to-SQL, knowledge
   graph and automation under enforced tenancy.
5. **Isolation is asserted, not demonstrated.** No published account was found of a comparable
   system's tenancy claim being adversarially tested and the results reported.

> **A judgement the literature does not make for us:** Karpukhin et al. show dense retrieval
> beats BM25 by 9–19%. We still use **both**. Dense retrieval captures *semantic similarity* —
> exactly the wrong property for an exact token such as an invoice number or "Section 7.3(b)".
> An invoice number is not semantically similar to anything; it must be matched literally.
> The two methods fail **complementarily**, so K-OS combines them.

---

## SLIDE 8 — Abstract & Objectives

**What K-OS is:** a multi-tenant platform unifying document ingestion, hybrid RAG, a fleet of
specialised agents, natural-language-to-SQL, a knowledge graph, workflow automation and a
collaborative code editor — behind one browser-based desktop interface.

- Every organisation that signs up receives an **isolated workspace**
- Every answer is grounded in that organisation's own documents
- Every answer carries **citations and an explicit confidence score**

**Objectives**

1. Multi-tenant platform with isolation enforced independently at application,
   query-rewriting and database layers
2. Hybrid RAG combining lexical and dense retrieval, returning citations + confidence
3. A fleet of specialised agents under a routing layer that parallelises where useful
4. Tabular content extracted into queryable SQL tables — quantitative questions answered by
   computation, not text similarity
5. Validation through a structured, evidence-based quality audit
6. **Honest degradation** — when the model provider fails, return grounded sources and say so

---

## SLIDE 9 — System Architecture: three-layer tenant isolation

**Layer 1 — ORM interceptor.** Applies a workspace predicate to every read and stamps every
write. Isolation cannot be forgotten in a single query — it is structural.

**Layer 2 — Fail-closed SQL guard.** Rewrites model-generated SQL so every tenant table
becomes a workspace-scoped subquery. Rejects any construct it cannot prove safe.

**Layer 3 — PostgreSQL Row-Level Security.** Executes as a dedicated NOLOGIN role under RLS
policies keyed to a per-request workspace setting. Rows outside the caller's workspace are
invisible to the executing role **regardless of the query text**.

Supporting pipeline: documents (PDF, DOCX, PPTX, XLSX, CSV, image, text) are parsed, chunked
with overlap, embedded and indexed. Tabular regions are materialised as real SQL tables so
structured questions bypass text chunking entirely.

*Layer 3 exists because Layer 2 was empirically shown to be insufficient — next slide.*

---

## SLIDE 10 — Key Finding *(strongest visual treatment)*

### An application-layer guard failed. In our own code. We found it, reproduced it, fixed it — then made the failure class structurally impossible.

- A **schema-qualified table reference** — `SELECT * FROM public.tasks` — evaded the guard's
  table-matching and executed **unscoped**
- It returned the records of **every workspace on the deployment**, including user identities
- Reproduced with two live tenants → corrected to fail closed → covered by regression tests
- **Layer 3 (RLS) then added.** Under it, an adversarial query carrying *no tenant predicate
  whatsoever* returned only the caller's own rows. The tenant registry was entirely unreadable.

> **This is the strongest justification the literature's recommendation could receive.**
> The guidance argues *from principle* that application-layer isolation is insufficient.
> We observed that insufficiency directly, in our own code, and moved the guarantee into
> the database.

---

## SLIDE 11 — Evaluation & Results

**Implementation scale** *(verified 1 Aug 2026)*

| Metric | Value |
|---|---|
| Backend (FastAPI + PostgreSQL) | ~14,500 lines |
| Frontend (React + TypeScript) | ~11,600 lines |
| REST endpoints · tables · apps · agents | 104 · 27 · 19 · 9 |
| Automated tests passing | **415** |
| Structured audit | 10 passes · 24 findings · all remediated |

**Measured outcomes**

| Outcome | Before | After |
|---|---|---|
| Task-board DB round trips (N+1) | 202 | **2** |
| Initial JavaScript payload | 861 KB | **302 KB** |
| Cross-tenant leak, unscoped query | Data exposed | **Only caller's rows** |

**Resilience** — with the model provider forced to fail on *every* call, no request failed:
the system returned cited source excerpts and declared the degradation. On an empty workspace
it stated no relevant material existed rather than fabricating. Unicode round-tripping
(Marathi, Chinese, RTL script, emoji, astral-plane) was byte-identical across API and database.

---

## SLIDE 12 — Limitations, Future Work & Conclusion

**Limitations (stated honestly)**

- Entity graph implements co-occurrence extraction, **not** the full community-summarisation
  pipeline of Edge et al. — too costly for interactive ingestion
- Retrieval quality **not** yet evaluated against a standard benchmark
- The user survey is limited in scale and purposively sampled — it *indicates* rather than
  *establishes* user preference
- Foundation-model training is out of scope; the system is model-agnostic by design

**Future work** — benchmark retrieval evaluation · per-row isolation for extracted tables ·
formal verification of the SQL guard · community-summarisation pipeline

### Conclusion

**The principal finding is empirical, not architectural.** An application-layer isolation
guard — of the kind widely relied upon in shared-schema multi-tenant systems — was shown to
fail on a lexical variation its author had not anticipated, exposing every tenant's data.
That such a failure is possible is the strongest available argument that a multi-tenant AI
platform must enforce isolation **in the database**, where correctness does not depend on
anticipating every form a generated query may take.

**References** *(small, two columns)*

1. P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," *NeurIPS*, vol. 33, pp. 9459–9474, 2020.
2. Y. Gao et al., "Retrieval-Augmented Generation for LLMs: A Survey," arXiv:2312.10997, 2023.
3. V. Karpukhin et al., "Dense Passage Retrieval for Open-Domain QA," *Proc. EMNLP*, pp. 6769–6781, 2020.
4. Z. Ji et al., "Survey of Hallucination in NLG," *ACM Comput. Surv.*, vol. 55, no. 12, art. 248, 2023.
5. S. Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models," *Proc. ICLR*, 2023.
6. T. Yu et al., "Spider: A Large-Scale Human-Labeled Dataset for Text-to-SQL," *Proc. EMNLP*, pp. 3911–3921, 2018.
7. D. Edge et al., "From Local to Global: A Graph RAG Approach," arXiv:2404.16130, Microsoft Research, 2024.
8. OWASP Foundation, "OWASP Top 10 for LLM Applications," 2025 ed.
9. McKinsey & Company, "The State of AI: Global Survey," QuantumBlack, 2025.
10. AWS, "Multi-tenant data isolation with PostgreSQL Row Level Security," AWS Database Blog, 2026.

---

## Keywords

Retrieval-Augmented Generation · Multi-Agent Systems · Multi-Tenant Architecture ·
Row-Level Security · Large Language Models · Text-to-SQL · Knowledge Graph ·
Enterprise Search · Data Isolation · Software Quality Assurance
