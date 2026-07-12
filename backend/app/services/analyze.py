"""Document analyzers — Resume / Contract / Invoice quick-actions.

Builds a structured scorecard for an indexed document: the LLM is asked for
strict JSON; when the provider is the mock (or returns garbage) a
deterministic heuristic scorecard is produced instead, so the demo always
works and tests are reproducible.
"""
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.provider import get_llm, safe_complete
from app.models import Chunk, DataTable, Document

KINDS = ("resume", "contract", "invoice", "auto")

_PROMPTS = {
    "resume": "You are a technical recruiter. Assess this resume: seniority, core skills, red flags, interview focus areas.",
    "contract": "You are a commercial lawyer. Assess this contract: parties, term, payment, liability, termination, risky clauses.",
    "invoice": "You are an accounts-payable auditor. Assess this invoice: vendor, totals, due date, line-item anomalies.",
    "auto": "You are a senior analyst. Assess this document: what it is, key figures, risks, and recommended follow-ups.",
}

_SCHEMA = (
    'Return ONLY strict JSON, no prose, matching: {"verdict": "<one line>", "score": <0-100>, '
    '"highlights": [{"label": "<short>", "value": "<short>", "status": "good|warn|bad"}], '
    '"summary": "<3-4 sentences>"} — 4 to 8 highlights.'
)

RX_MONEY = re.compile(r"(?:\$|₹|€|£)\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|INR|EUR)\b")
RX_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
RX_DATE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})\b")
RX_RISK = re.compile(r"\b(termination|liability|indemnif|penalt|breach|arbitration|non-compete|confidential)\w*\b", re.I)
RX_SKILL = re.compile(r"\b(python|java(script)?|typescript|react|sql|docker|kubernetes|aws|fastapi|ml|ai|langchain)\b", re.I)


def _doc_text(db: Session, doc: Document, limit: int = 14) -> str:
    chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ord).limit(limit)
    ).all()
    text = "\n\n".join(c.text for c in chunks)[:9000]
    tables = db.scalars(select(DataTable).where(DataTable.document_id == doc.id)).all()
    if tables:
        text += "\n\nSTRUCTURED TABLES: " + "; ".join(
            f"{t.table_name} ({t.title}, {t.row_count} rows, columns {t.columns})" for t in tables
        )
    return text


def _heuristic(kind: str, doc: Document, text: str) -> dict:
    money = RX_MONEY.findall(text)[:4]
    emails = RX_EMAIL.findall(text)[:2]
    dates = RX_DATE.findall(text)[:3]
    risks = sorted({m.group(0).lower() for m in RX_RISK.finditer(text)})[:5]
    skills = sorted({m.group(0).lower() for m in RX_SKILL.finditer(text)})[:8]
    words = len(text.split())

    hl: list[dict] = [{"label": "Length", "value": f"{words} words · {doc.chunk_count} chunks", "status": "good" if words > 120 else "warn"}]
    if kind == "resume":
        hl.append({"label": "Skills detected", "value": ", ".join(skills) or "none found", "status": "good" if len(skills) >= 3 else "warn"})
        hl.append({"label": "Contact", "value": ", ".join(emails) or "no email found", "status": "good" if emails else "bad"})
        score = min(95, 40 + 6 * len(skills) + (10 if emails else 0))
        verdict = "Screen-worthy technical profile" if len(skills) >= 3 else "Needs a closer manual read"
    elif kind == "contract":
        hl.append({"label": "Risk clauses", "value": ", ".join(risks) or "none detected", "status": "warn" if risks else "good"})
        hl.append({"label": "Dates found", "value": ", ".join(dates) or "none", "status": "good" if dates else "warn"})
        hl.append({"label": "Amounts", "value": ", ".join(money) or "none", "status": "good" if money else "warn"})
        score = max(30, 90 - 8 * len(risks))
        verdict = f"{len(risks)} risk-bearing clause type(s) flagged" if risks else "No obvious risk language detected"
    elif kind == "invoice":
        hl.append({"label": "Amounts", "value": ", ".join(money) or "no amounts found", "status": "good" if money else "bad"})
        hl.append({"label": "Dates", "value": ", ".join(dates) or "no dates found", "status": "good" if dates else "warn"})
        score = min(95, 30 + 25 * min(2, len(money)) + (15 if dates else 0))
        verdict = "Totals located — verify against PO" if money else "Amounts missing: manual review required"
    else:
        if money:
            hl.append({"label": "Amounts", "value": ", ".join(money), "status": "good"})
        if risks:
            hl.append({"label": "Risk terms", "value": ", ".join(risks), "status": "warn"})
        if skills:
            hl.append({"label": "Tech terms", "value": ", ".join(skills), "status": "good"})
        score = 70
        verdict = f"General document · type '{doc.doc_type}'"
    return {
        "verdict": verdict,
        "score": int(score),
        "highlights": hl,
        "summary": (
            f"Deterministic heuristic analysis of '{doc.title}' ({doc.doc_type}, {doc.chunk_count} chunks). "
            f"Detected {len(money)} amount(s), {len(dates)} date(s), {len(risks)} risk term(s) and {len(skills)} skill term(s). "
            "Configure a real LLM key for a full reasoning-based assessment."
        ),
        "engine": "heuristic",
    }


def _parse(raw: str) -> dict | None:
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(raw[start:end + 1])
        if not isinstance(data.get("highlights"), list) or "verdict" not in data:
            return None
        data["score"] = max(0, min(100, int(data.get("score", 50))))
        data["highlights"] = [
            {"label": str(h.get("label", ""))[:60], "value": str(h.get("value", ""))[:160],
             "status": h.get("status") if h.get("status") in ("good", "warn", "bad") else "warn"}
            for h in data["highlights"][:8] if isinstance(h, dict)
        ]
        data["summary"] = str(data.get("summary", ""))[:1200]
        data["verdict"] = str(data["verdict"])[:160]
        data["engine"] = "llm"
        return data
    except Exception:  # noqa: BLE001
        return None


def analyze_document(db: Session, doc: Document, kind: str) -> dict:
    kind = kind if kind in KINDS else "auto"
    text = _doc_text(db, doc)
    if get_llm().name != "mock":
        raw = safe_complete(
            f"{_PROMPTS[kind]} {_SCHEMA}",
            f"DOCUMENT '{doc.title}' ({doc.doc_type}):\n{text}\n\nJSON:",
        )
        parsed = _parse(raw)
        if parsed:
            parsed["kind"] = kind
            return parsed
    result = _heuristic(kind, doc, text)
    result["kind"] = kind
    return result
