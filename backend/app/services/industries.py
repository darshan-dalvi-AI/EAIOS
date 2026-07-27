"""Industry personalisation.

A generic AI workspace forces every customer to imagine what it could do for
*their* business. That gap is where trials die. This module closes it: the
company says what it does, and the workspace configures itself — specialist
agents written for that field, the questions their staff actually ask, an
automation for their most repetitive task, and the right document analyser.

Applied once at onboarding, it turns an empty product into something that
looks purpose-built within a minute of signing up.

Everything created here is ordinary tenant data (custom agents, workflows),
so it is org-scoped, editable, deletable, and carries no special privileges.
"""
import json
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CustomAgent, Document, Organization, Task, User, Workflow

log = logging.getLogger("eaios.industries")


def _agent(slug: str, name: str, description: str, hue: int, prompt: str,
           tools: tuple[str, ...] = ("rag",)) -> dict:
    return {"slug": slug, "name": name, "description": description, "hue": hue,
            "system_prompt": prompt, "tools": list(tools)}


def _flow(name: str, description: str, agent: str, instruction: str,
          trigger: str = "upload") -> dict:
    """A minimal but genuinely runnable workflow: trigger → agent → notify."""
    return {
        "name": name, "description": description, "trigger": trigger,
        "nodes": [
            {"id": "n1", "type": "trigger", "x": 60, "y": 120, "data": {"trigger": trigger}},
            {"id": "n2", "type": "agent", "x": 320, "y": 120,
             "data": {"agent": agent, "prompt": instruction}},
            {"id": "n3", "type": "notify", "x": 580, "y": 120,
             "data": {"message": f"{name} finished"}},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    }


# ── the catalogue ────────────────────────────────────────────────────────
# Each profile is written for how that industry actually talks: the agent
# prompts name their documents, their obligations and their failure modes.
INDUSTRIES: dict[str, dict] = {
    "it_services": {
        "name": "IT Services & Consulting",
        "tagline": "Client documentation, runbooks and delivery evidence",
        "icon": "Briefcase", "hue": 200,
        "value": "Answer client questions from their own contracts and runbooks, with an audit trail of exactly what was used.",
        "agents": [
            _agent("sow-analyst", "SOW Analyst", "Reads statements of work and flags scope, dates and penalties", 200,
                   "You analyse statements of work and client contracts for an IT services firm. For any question, "
                   "identify: agreed scope and explicit exclusions, delivery milestones and dates, acceptance criteria, "
                   "penalty or service-credit clauses, and change-request procedure. Quote the exact clause you rely on. "
                   "If the documents do not settle the question, say so plainly rather than inferring."),
            _agent("runbook-engineer", "Runbook Engineer", "Turns incident notes into step-by-step recovery procedures", 155,
                   "You write and explain operational runbooks. Answer with numbered, verifiable steps, each stating its "
                   "prerequisite and how to confirm it worked. Call out irreversible actions before the step that performs "
                   "them. Where the knowledge base lacks a step, mark it clearly as a gap rather than inventing it."),
        ],
        "prompts": [
            "What is in scope for the current client SOW, and what is explicitly excluded?",
            "Summarise our incident response runbook for a database failover.",
            "Which client contracts have service credits, and at what thresholds?",
            "Draft a status update for this week's delivery milestones.",
        ],
        "workflow": _flow("Contract intake review", "Every uploaded contract gets a scope-and-risk summary",
                          "document", "Summarise scope, key dates, payment terms and any penalty clauses."),
        "analyzer": "contract",
    },
    "healthcare": {
        "name": "Healthcare & Clinics",
        "tagline": "Protocols, patient information and compliance",
        "icon": "HeartPulse", "hue": 350,
        "value": "Staff get protocol answers with citations, and every access to personal data is recorded automatically.",
        "agents": [
            _agent("protocol-assistant", "Protocol Assistant", "Answers strictly from approved clinical protocols", 350,
                   "You answer questions using ONLY the clinical protocols and policies in this knowledge base. "
                   "Always cite the protocol name and section. You do not provide medical advice, diagnosis or "
                   "treatment recommendations beyond quoting the approved document — if a question goes further, "
                   "state that it requires a qualified clinician. If the protocols are silent, say so explicitly; "
                   "never fill the gap from general knowledge."),
            _agent("compliance-officer", "Compliance Assistant", "Checks documents against retention and privacy rules", 38,
                   "You review documents and processes against healthcare privacy and record-keeping obligations. "
                   "Identify personal or sensitive data, state the retention requirement that applies, and flag anything "
                   "that appears to be stored or shared beyond its stated purpose. Be precise about what the document "
                   "says versus what you are inferring."),
        ],
        "prompts": [
            "What is our documented protocol for patient intake?",
            "Which of our policies mention data retention periods?",
            "Summarise the consent requirements described in our documents.",
            "What does our infection-control policy require for equipment cleaning?",
        ],
        "workflow": _flow("Policy change review", "Flags privacy and retention implications when a policy is uploaded",
                          "document", "Identify any personal data handling, retention period and consent requirement described."),
        "analyzer": "auto",
        "compliance_note": "Personal-data access auditing is on by default for this profile.",
    },
    "legal": {
        "name": "Legal & Professional Services",
        "tagline": "Contracts, obligations, precedent and deadlines",
        "icon": "Scale", "hue": 265,
        "value": "Find the clause, the obligation and the deadline across every agreement you hold — with the source attached.",
        "agents": [
            _agent("clause-finder", "Clause Finder", "Locates and compares clauses across agreements", 265,
                   "You locate and compare contractual clauses. For each answer give: the exact clause text, the document "
                   "and section it came from, and a plain-English restatement. When comparing agreements, present the "
                   "differences as a list. You are not giving legal advice — you are reporting what the documents say, "
                   "and you say so when a question requires judgement rather than retrieval."),
            _agent("obligation-tracker", "Obligation Tracker", "Extracts duties, deadlines and renewal dates", 15,
                   "You extract obligations from agreements: who must do what, by when, and what happens if they do not. "
                   "Present them as a table ordered by deadline. Always cite the clause. Flag any obligation whose "
                   "trigger or deadline is ambiguous in the source text rather than guessing a date."),
        ],
        "prompts": [
            "Which agreements renew automatically, and what is the notice period?",
            "Compare the limitation-of-liability clauses across our contracts.",
            "List every obligation with a deadline in the next quarter.",
            "What are our termination rights in the current vendor agreement?",
        ],
        "workflow": _flow("New agreement triage", "Extracts obligations and dates whenever an agreement is uploaded",
                          "document", "Extract every obligation, deadline, renewal date and termination right."),
        "analyzer": "contract",
    },
    "finance": {
        "name": "Finance & Accounting",
        "tagline": "Invoices, statements and reporting",
        "icon": "Landmark", "hue": 38,
        "value": "Spreadsheets become queryable tables, and 'revenue by region as a bar chart' is a sentence, not a ticket.",
        "agents": [
            _agent("invoice-auditor", "Invoice Auditor", "Checks invoices for totals, tax and duplicate risk", 38,
                   "You audit invoices and financial documents. For each, report: supplier, invoice number, date, "
                   "currency, net, tax and gross totals, payment terms, and whether the arithmetic is internally "
                   "consistent. Flag missing fields, unusual totals and anything that looks like a duplicate of another "
                   "document in the knowledge base. Never silently correct a figure — report the discrepancy."),
            _agent("reporting-analyst", "Reporting Analyst", "Answers numeric questions from extracted tables", 145,
                   "You answer quantitative questions using the structured tables extracted from uploaded spreadsheets "
                   "and statements. Show the figures you used and the table they came from. State the period covered. "
                   "If a number cannot be derived from the available data, say which input is missing."),
        ],
        "prompts": [
            "Show revenue by region as a bar chart.",
            "Which invoices are overdue, and by how many days?",
            "Summarise expenses by category for the last quarter.",
            "Are there any duplicate invoices in what we have uploaded?",
        ],
        "workflow": _flow("Invoice intake", "Every uploaded invoice gets an automatic audit summary",
                          "document", "Extract supplier, invoice number, dates, totals and payment terms; flag anomalies."),
        "analyzer": "invoice",
    },
    "hr_staffing": {
        "name": "HR & Staffing",
        "tagline": "Policies, handbooks and candidate screening",
        "icon": "Users", "hue": 150,
        "value": "Policy questions answer themselves with citations, and candidate CVs get a consistent scorecard.",
        "agents": [
            _agent("policy-desk", "Policy Desk", "Answers staff policy questions with the exact clause", 150,
                   "You answer employee questions from the company handbook and HR policies. Always quote the policy "
                   "section you relied on and state its effective date if present. Where a policy depends on location, "
                   "grade or contract type, ask which applies rather than assuming. If a question concerns an individual "
                   "case rather than policy, direct the person to HR instead of speculating."),
            _agent("cv-screener", "CV Screener", "Scores candidates consistently against a role description", 265,
                   "You screen candidate CVs against a role description. Produce: years of relevant experience, matched "
                   "and missing required skills, notable gaps or overlaps in dates, and a short evidence-based summary. "
                   "Judge only what the document evidences. Do not infer or comment on age, gender, nationality, "
                   "marital status, health or any other protected characteristic."),
        ],
        "prompts": [
            "How many annual leave days do we get, and do they carry forward?",
            "What is our notice period for a permanent employee?",
            "Screen the uploaded CV against our backend engineer role.",
            "What does our policy say about remote working?",
        ],
        "workflow": _flow("CV intake screening", "Scores each uploaded CV against the current role description",
                          "document", "Score this candidate: relevant experience, matched skills, missing skills, summary."),
        "analyzer": "resume",
    },
    "manufacturing": {
        "name": "Manufacturing & Operations",
        "tagline": "SOPs, quality records and maintenance",
        "icon": "Factory", "hue": 25,
        "value": "Operators get the right procedure step in seconds instead of hunting through a binder.",
        "agents": [
            _agent("sop-guide", "SOP Guide", "Returns the exact procedure step, in order", 25,
                   "You answer from standard operating procedures and work instructions. Reply with the specific numbered "
                   "steps that apply, in order, including any safety precaution that precedes them. Always name the SOP "
                   "and revision. If the procedure in the knowledge base is superseded or ambiguous, say so — an operator "
                   "acting on a wrong step is worse than an unanswered question."),
            _agent("quality-analyst", "Quality Analyst", "Reads inspection and non-conformance records", 145,
                   "You analyse quality records, inspection reports and non-conformance logs. Identify the defect, the "
                   "affected batch or line, the stated root cause and the corrective action, and whether the record shows "
                   "the action was verified. Highlight records where a corrective action has no verification."),
        ],
        "prompts": [
            "What is the changeover procedure for line 2?",
            "Which non-conformances are still open without a verified corrective action?",
            "What PPE does the welding SOP require?",
            "Summarise last month's inspection findings by defect type.",
        ],
        "workflow": _flow("Quality record intake", "Summarises each uploaded inspection or NCR",
                          "document", "Extract defect, batch, root cause, corrective action and verification status."),
        "analyzer": "auto",
    },
    "education": {
        "name": "Education & Training",
        "tagline": "Curriculum, course material and assessment",
        "icon": "GraduationCap", "hue": 210,
        "value": "Turn course material into explanations, question banks and study guides that stay on-syllabus.",
        "agents": [
            _agent("curriculum-tutor", "Curriculum Tutor", "Explains material strictly within the syllabus", 210,
                   "You explain concepts using only the uploaded course material. Give a short definition, a worked "
                   "example, and a common misconception. Cite the module or chapter. If a question goes beyond the "
                   "syllabus in the knowledge base, say so and answer only the part the material covers."),
            _agent("assessment-writer", "Assessment Writer", "Drafts questions mapped to learning outcomes", 285,
                   "You draft assessment questions from the uploaded material. For each question give the learning "
                   "outcome it tests, the difficulty, the answer, and the section it is drawn from. Produce a mix of "
                   "recall, application and analysis. Never write a question the material cannot answer."),
        ],
        "prompts": [
            "Explain the key concepts in module 3 with an example.",
            "Generate ten exam questions covering this week's material.",
            "Which learning outcomes does the current syllabus not assess?",
            "Create a revision summary for the uploaded chapter.",
        ],
        "workflow": _flow("Course material intake", "Builds a summary and question set from new material",
                          "document", "Summarise key concepts and draft five assessment questions with answers."),
        "analyzer": "auto",
    },
    "real_estate": {
        "name": "Real Estate & Property",
        "tagline": "Leases, listings and property records",
        "icon": "Building2", "hue": 175,
        "value": "Every lease obligation, rent review and break clause, findable in one question.",
        "agents": [
            _agent("lease-analyst", "Lease Analyst", "Extracts terms, rent reviews and break clauses", 175,
                   "You analyse leases and property agreements. For each, report: parties, demised premises, term, rent "
                   "and review mechanism, break clauses and their conditions, repair obligations, and permitted use. "
                   "Quote the clause. Flag any condition attached to a break right, since an unmet condition invalidates it."),
            _agent("portfolio-diary", "Portfolio Diary", "Tracks rent reviews, break notices and renewal deadlines", 42,
                   "You track dates and obligations across a property portfolio. For any question about timing, list every "
                   "relevant date with the property, the clause it comes from, and the notice period required to act on it — "
                   "then state the last date on which notice can still be given. Treat a missed notice deadline as the most "
                   "serious outcome: say plainly when a deadline has already passed rather than softening it."),
        ],
        "prompts": [
            "Which leases have a rent review in the next twelve months?",
            "What are the break clause conditions on the current lease?",
            "Summarise repair obligations across our portfolio.",
            "What is the permitted use under this agreement?",
        ],
        "workflow": _flow("Lease intake", "Extracts key dates and obligations from each uploaded lease",
                          "document", "Extract parties, term, rent review dates, break clauses and repair obligations."),
        "analyzer": "contract",
    },
    "retail": {
        "name": "Retail & E-commerce",
        "tagline": "Suppliers, catalogues and operations",
        "icon": "ShoppingBag", "hue": 320,
        "value": "Supplier terms and product data become answerable, and sales spreadsheets become live charts.",
        "agents": [
            _agent("supplier-desk", "Supplier Desk", "Answers from supplier agreements and price lists", 320,
                   "You answer questions about suppliers using their agreements, price lists and terms. Report pricing "
                   "tiers, minimum order quantities, lead times, return and warranty terms, and quote the source. "
                   "Flag where two documents disagree about the same supplier rather than choosing one silently."),
            _agent("merchandising-analyst", "Merchandising Analyst", "Answers sales questions from uploaded data", 145,
                   "You answer commercial questions from uploaded sales, stock and catalogue data. Show the figures you "
                   "used and name the table they came from, and always state the period covered. Distinguish between a "
                   "genuine trend and normal variation: if a conclusion rests on few data points or a short window, say "
                   "so in the answer. When a question needs a figure that is not in the uploaded data — margin, cost of "
                   "goods, returns reason — name the missing input instead of estimating it."),
        ],
        "prompts": [
            "Show sales by category as a bar chart.",
            "What are the lead times and minimum order quantities per supplier?",
            "Which products have the highest return rate?",
            "Summarise our supplier return and warranty terms.",
        ],
        "workflow": _flow("Supplier document intake", "Summarises terms whenever a supplier document is uploaded",
                          "document", "Extract pricing tiers, minimum order quantity, lead time, and return terms."),
        "analyzer": "invoice",
    },
    "general": {
        "name": "Something else",
        "tagline": "A balanced starting point you can shape yourself",
        "icon": "Sparkles", "hue": 265,
        "value": "A general research and reporting pair, ready to specialise as you add your documents.",
        "agents": [
            _agent("knowledge-desk", "Knowledge Desk", "Answers company questions with citations", 265,
                   "You answer questions using the organisation's uploaded documents. Always cite the document and "
                   "section. State clearly when the knowledge base does not contain the answer rather than filling the "
                   "gap from general knowledge."),
            _agent("report-writer", "Report Writer", "Turns findings into a structured summary", 210,
                   "You write concise structured reports from retrieved material. Use this shape: purpose, findings "
                   "(each with its citation), risks or open questions, and recommended next steps. Every factual claim "
                   "must be traceable to a source in the knowledge base — if a section of the report has no supporting "
                   "document, write that the evidence is missing rather than filling it with plausible text. Keep the "
                   "tone plain and factual, and put the most decision-relevant finding first."),
        ],
        "prompts": [
            "What are the key points in the documents we uploaded?",
            "Summarise our policies for a new joiner.",
            "What obligations or deadlines appear in our documents?",
            "Draft a summary report of this month's uploads.",
        ],
        "workflow": _flow("Document intake summary", "Summarises every uploaded document",
                          "document", "Summarise this document: purpose, key points, any dates or obligations."),
        "analyzer": "auto",
    },
}


def catalogue() -> list[dict]:
    """Public view — what the picker shows, without the prompt internals."""
    return [
        {
            "id": key,
            "name": p["name"],
            "tagline": p["tagline"],
            "icon": p["icon"],
            "hue": p["hue"],
            "value": p["value"],
            "agents": [{"name": a["name"], "description": a["description"]} for a in p["agents"]],
            "prompts": p["prompts"][:3],
            "workflow": p["workflow"]["name"],
            "analyzer": p["analyzer"],
        }
        for key, p in INDUSTRIES.items()
    ]


def get(industry_id: str) -> dict | None:
    return INDUSTRIES.get(industry_id)


SAMPLE_TAG = "sample"


def stage_starter_documents(db: Session, industry_id: str, user: User) -> tuple[list[str], list[tuple[str, object]]]:
    """Create the corpus rows and write the files — the fast half.

    Split from indexing because of where this runs. The database is in another
    region, so *every statement is a round trip*; parsing three documents into
    chunks and entities is a few hundred of them, and uploading each file to
    object storage adds more. Doing all that inside the request meant a visitor
    watched a spinner for twenty seconds before their workspace appeared.

    So this half — insert the rows, write the files, one commit — happens now,
    and ``index_documents`` finishes the slow part behind the response. The
    interface already polls while anything is ``queued``, and the caller still
    learns the exact titles, so nothing has to lie about what was created.

    Returns ``(titles, pending)`` where pending is what ``index_documents`` needs.
    """
    import os

    from app.core.config import settings
    from app.services import industry_packs

    docs = industry_packs.for_industry(industry_id)
    if not docs:
        return [], []

    # Never seed twice — re-running the wizard must not duplicate the corpus.
    # But choosing a *different* field should swap it: a clinic that started on
    # the general pack, or a workspace correcting a mis-click, must not be left
    # answering questions out of the wrong industry's documents.
    stale: list[str] = []
    already = db.scalar(select(Document).where(Document.tags.contains(SAMPLE_TAG)))
    if already:
        if industry_id in (already.tags or "").split(","):
            return [], []
        # Rows go now — the list must be honest the moment the response lands.
        # Their vectors, tables, entities and stored files are torn down with
        # the indexing, behind the response: three deletes against object
        # storage in another region is not something to make anyone watch.
        stale = drop_sample_rows(db)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    titles: list[str] = []
    jobs: list[tuple[str, object]] = []
    for title, text in docs:
        # A comma-separated first line with no markdown heading is tabular data:
        # ingesting it as CSV makes it a real table the SQL agent can chart.
        first = text.lstrip().split("\n", 1)[0]
        dtype = "csv" if ("," in first and not first.startswith("#")) else "txt"
        doc = Document(
            filename=f"sample_{industry_id}_{len(titles)}.{dtype}",
            title=title[:255], doc_type=dtype, owner_id=user.id, status="queued",
            tags=f"{SAMPLE_TAG},{industry_id}",
        )
        db.add(doc)
        db.flush()          # assigns the id without a round trip of its own

        dest = os.path.join(settings.UPLOAD_DIR, f"{doc.id}.{dtype}")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(text)
        doc.size_bytes = os.path.getsize(dest)

        titles.append(title)
        jobs.append(("index", (doc.id, dest)))
    db.commit()             # one commit for the whole corpus, not two per file
    if stale:
        # Carried alongside the indexing so the caller defers both together.
        jobs.insert(0, ("cleanup", stale))
    return titles, jobs


def index_documents(jobs: list[tuple[str, object]]) -> None:
    """The slow half: parse, chunk, embed, index, and mirror to object storage.

    Runs after the response has gone out, on its own session — the request's
    session is closed by then. Failures are logged and dropped: a starter
    document that will not index is a worse demo, not a broken workspace.
    """
    if not jobs:
        return

    from app.core import storage
    from app.core.database import SessionLocal
    from app.rag import pipeline

    for kind, payload in jobs:
        if kind == "cleanup":
            cleanup_sample_artifacts(payload)   # type: ignore[arg-type]
            continue
        doc_id, path = payload                  # type: ignore[misc]
        try:
            pipeline.ingest_document(doc_id, path)
            storage.put(os.path.basename(path), path)
        except Exception as exc:   # noqa: BLE001 — never let onboarding fail on a sample
            # The other half of the swap race: the visitor may have changed
            # industry while this was running, taking the document out from
            # under us. That is not a failure — the row is meant to be gone.
            with SessionLocal() as db:
                doc = db.get(Document, doc_id)
                if doc is None:
                    log.info("starter document %s was removed while indexing", doc_id)
                    continue
                log.warning("starter document %s failed to index: %s", doc_id, exc)
                if doc.status != "indexed":
                    doc.status = "failed"
                    doc.error = str(exc)[:500]
                    db.commit()


def seed_starter_documents(db: Session, industry_id: str, user: User) -> list[str]:
    """Stage and index in one go — for callers with no response to get out of
    the way of (the seed script, tests, anything not serving a request)."""
    titles, jobs = stage_starter_documents(db, industry_id, user)
    index_documents(jobs)
    return titles


def _seed_checklist(db: Session, industry_id: str, user: User) -> list[str]:
    """Put a first-week route through the product on the task board."""
    from app.services import industry_packs

    if db.scalar(select(Task).where(Task.source == "onboarding")):
        return []
    items = industry_packs.checklist_for(industry_id)
    for title in items:
        db.add(Task(title=title[:400], status="todo", source="onboarding", owner_id=user.id))
    return items


def drop_sample_rows(db: Session) -> list[tuple[str, str]]:
    """Remove the sample documents from the workspace — rows only, one commit.

    Deleting the *rows* is what the customer sees, and it has to happen before
    the response so the count and the document list tell the truth. Tearing
    down the artefacts behind them (vectors, materialised tables, graph
    entities, the stored file) is slower and invisible, so it is a separate
    step the caller can defer.
    """
    from sqlalchemy import delete as sql_delete

    from app.models import Chunk

    docs = list(db.scalars(select(Document).where(Document.tags.contains(SAMPLE_TAG))))
    if not docs:
        return []
    handles = [(d.id, f"{d.id}{os.path.splitext(d.filename)[1].lower()}") for d in docs]
    ids = [d.id for d in docs]

    # Bulk, in this order, in one transaction — deliberately not the ORM's
    # per-object cascade.
    #
    # These documents may still be indexing in the background when a visitor
    # swaps industry seconds after opening the demo. The ORM cascade loads the
    # chunks, deletes them, then deletes the document — and a chunk inserted by
    # the indexer in between makes that final delete violate the foreign key.
    # PostgreSQL enforces it and rejects the whole request; SQLite does not,
    # which is why this only ever appeared in production.
    db.execute(sql_delete(Chunk).where(Chunk.document_id.in_(ids)))
    db.execute(sql_delete(Document).where(Document.id.in_(ids)))
    db.commit()
    return handles


def cleanup_sample_artifacts(handles: list[tuple[str, str]]) -> None:
    """The invisible half of removing a sample: vectors, tables, graph entities
    and the stored file. Safe to run after the response, on its own session."""
    if not handles:
        return

    from app.core import storage
    from app.core.database import SessionLocal
    from app.rag import pipeline
    from app.rag import tables as dtables
    from app.services import kgraph

    with SessionLocal() as db:
        for doc_id, key in handles:
            try:
                pipeline.delete_document_vectors(doc_id)
                dtables.drop_for_document(db, doc_id)
                kgraph.forget_document(db, doc_id)
                storage.remove(key)
            except Exception:   # noqa: BLE001 — the row is already gone; this is tidying
                log.warning("partial cleanup for sample document %s", doc_id)
        db.commit()


def remove_samples(db: Session, user: User) -> int:
    """Delete the seeded starter corpus, artefacts and all. Their call."""
    handles = drop_sample_rows(db)
    cleanup_sample_artifacts(handles)
    log.info("removed %d sample document(s) for %s", len(handles), user.email)
    return len(handles)


def apply(db: Session, org: Organization, industry_id: str, user: User,
          with_samples: bool = True, defer: bool = False) -> dict:
    """Configure a workspace for its industry. Idempotent — re-running the
    wizard refines the workspace rather than duplicating it."""
    profile = INDUSTRIES.get(industry_id)
    if profile is None:
        raise ValueError(f"Unknown industry '{industry_id}'")

    created_agents, created_flows = [], []

    for spec in profile["agents"]:
        exists = db.scalar(select(CustomAgent).where(CustomAgent.slug == spec["slug"]))
        if exists:
            continue
        db.add(CustomAgent(
            slug=spec["slug"], name=spec["name"], description=spec["description"],
            system_prompt=spec["system_prompt"], tools=json.dumps(spec["tools"]),
            hue=spec["hue"], owner_id=user.id,
        ))
        created_agents.append(spec["name"])

    wf = profile["workflow"]
    if not db.scalar(select(Workflow).where(Workflow.name == wf["name"])):
        db.add(Workflow(
            name=wf["name"], description=wf["description"], owner_id=user.id,
            trigger=wf["trigger"], nodes=json.dumps(wf["nodes"]), edges=json.dumps(wf["edges"]),
            enabled=False,   # visible and ready, but the customer decides when it runs
        ))
        created_flows.append(wf["name"])

    org.industry = industry_id
    db.commit()

    tasks_created = _seed_checklist(db, industry_id, user)
    db.commit()
    # Corpus last: it is the slow step, and everything above should be
    # committed even if it has trouble. When `defer` is set the caller takes
    # the indexing away to run after the response — the rows and files still
    # exist by the time this returns, so the reported titles are true either way.
    docs_created: list[str] = []
    pending: list[tuple[str, object]] = []
    if with_samples:
        docs_created, pending = stage_starter_documents(db, industry_id, user)
        if not defer:
            index_documents(pending)

    log.info("workspace %s configured for %s (%d agents, %d workflows, %d docs, %d tasks)",
             org.slug, industry_id, len(created_agents), len(created_flows),
             len(docs_created), len(tasks_created))
    return {
        "industry": industry_id,
        "name": profile["name"],
        "hue": profile["hue"],
        "value": profile["value"],
        "agents_created": created_agents,
        "workflows_created": created_flows,
        "documents_created": docs_created,
        "tasks_created": tasks_created,
        "prompts": profile["prompts"],
        "analyzer": profile["analyzer"],
        "compliance_note": profile.get("compliance_note", ""),
        # Returned rather than stashed in module state: the caller schedules it
        # after the response, and two concurrent signups can't collide.
        "_pending_index": pending,
    }
