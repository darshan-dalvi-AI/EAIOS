"""Knowledge graph — entity extraction on ingest + graph-augmented retrieval.

Deterministic, dependency-free NER (regex + heuristics) keeps ingestion fast
and the demo reproducible; the extraction function is the single seam where a
spaCy/LLM extractor can slot in later.

Graph model: ``Entity`` nodes, ``EntityEdge`` co-occurrence edges (weight =
number of chunks where both appear), ``EntityMention`` links entities to
chunks/documents so relational questions can cite real passages.
"""
import logging
import re
from collections import Counter
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, Entity, EntityEdge, EntityMention

log = logging.getLogger("eaios.kgraph")

# ── extraction ───────────────────────────────────────────────────────────
RX_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
RX_PHONE = re.compile(r"(?<![\d.])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,5}\)[\s.-]?)?\d{2,5}(?:[\s.-]\d{2,5}){1,4}(?![\d.])")
RX_MONEY = re.compile(r"(?:\$|₹|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|K|M|million|billion|lakh|crore))?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|INR|EUR)\b")
RX_PROPER = re.compile(r"\b(?:[A-Z][a-z]{2,}|[A-Z]{2,6})(?:[ \-](?:[A-Z][a-z]{2,}|[A-Z]{2,6}|of|for|the|&)){0,3}\b")
RX_ACRONYM = re.compile(r"^[A-Z]{2,6}$")

STOP = {
    "The", "This", "That", "These", "Those", "There", "Here", "When", "Where", "What", "Which", "While",
    "After", "Before", "Please", "Note", "For", "And", "But", "All", "Any", "Our", "Your", "You", "We",
    "May", "Must", "Should", "Can", "Will", "Not", "New", "Use", "See", "Each", "Every", "Section",
    "Page", "Table", "Figure", "Chapter", "Part", "Step", "Item", "Total", "Date", "Name", "From",
    "Subject", "Dear", "Regards", "Thanks", "Hello", "Also", "However", "Therefore", "During", "Within",
    "PDF", "DOCX", "PPTX", "XLSX", "CSV", "FAQ", "USD", "INR", "EUR",
}
ORG_HINTS = re.compile(r"\b(Inc|Corp|Corporation|Ltd|LLC|LLP|Team|Department|Dept|Committee|Division|Group|Technologies|Systems|Solutions|University|Institute)\b")
PERSON_HINTS = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof)\.? [A-Z]")
MONTHS = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b")


# PII: entity types treated as sensitive, personally identifiable — access
# to these through agents/graph queries is flagged in the audit log.
SENSITIVE_TYPES = {"person", "email", "phone"}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _phoneish(name: str) -> bool:
    """Phone heuristic: matching shape + 8-13 digits + a phone-y marker
    (leading +, parentheses, or ≥2 separators) to avoid number-pair noise."""
    if not RX_PHONE.fullmatch(name) or not 8 <= len(_digits(name)) <= 13:
        return False
    return "+" in name or "(" in name or len(re.findall(r"[\s.-]", name)) >= 2


def _classify(name: str, text: str) -> str:
    if RX_EMAIL.fullmatch(name):
        return "email"
    if _phoneish(name):
        return "phone"
    if ORG_HINTS.search(name):
        return "org"
    if RX_MONEY.fullmatch(name):
        return "money"
    if MONTHS.search(name) or re.fullmatch(r"(19|20)\d\d", name):
        return "date"
    if RX_ACRONYM.fullmatch(name):
        return "acronym"
    if PERSON_HINTS.search(f"x {name}") or re.search(rf"(Mr|Mrs|Ms|Dr|Prof)\.? {re.escape(name)}", text):
        return "person"
    if " " in name and name.istitle():
        return "concept"
    return "term"


def extract_entities(text: str, max_entities: int = 12) -> list[tuple[str, str]]:
    """→ [(name, type)] most frequent first, capped per chunk."""
    counts: Counter[str] = Counter()
    for match in RX_EMAIL.findall(text):
        counts[match.lower()] += 2
    for match in RX_PHONE.findall(text):
        m = match.strip()
        if _phoneish(m):
            counts[m] += 2
    for match in RX_MONEY.findall(text):
        counts[match.strip()] += 1
    for match in RX_PROPER.findall(text):
        name = re.sub(r"\s+", " ", match).strip(" -&")
        if name in STOP or len(name) < 3:
            continue
        if " " not in name and not name.isupper():
            # Single title-case words are usually just sentence-start capitalization.
            # Keep only if they recur, or appear mid-sentence (after a lowercase char).
            if len(re.findall(rf"\b{re.escape(name)}\b", text)) < 2 and not re.search(
                rf"[a-z][,;:()\"'\s]+{re.escape(name)}\b", text
            ):
                continue
        counts[name] += 1
    ranked = [name for name, _ in counts.most_common(max_entities)]
    return [(name, _classify(name, text)) for name in ranked]


# ── indexing (called from the ingestion pipeline) ────────────────────────
def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()[:200]


def index_chunks(db: Session, doc: Document, chunks: list[Chunk]) -> int:
    """Extract entities from freshly indexed chunks and merge into the graph."""
    # reindex hygiene: drop this document's previous mentions + edges
    db.query(EntityMention).filter(EntityMention.document_id == doc.id).delete()
    db.query(EntityEdge).filter(EntityEdge.doc_id == doc.id).delete()

    cache: dict[str, Entity] = {}

    GENERIC = {"term", "concept"}

    def upsert(name: str, etype: str) -> Entity:
        key = _norm(name)
        if key in cache:
            entity = cache[key]
        else:
            entity = db.scalar(select(Entity).where(Entity.key == key))
            if entity is None:
                entity = Entity(name=name[:200], key=key, etype=etype)
                db.add(entity)
                db.flush()
            cache[key] = entity
        # type refinement: new evidence can promote a generic entity to a
        # specific class (e.g. 'concept' → 'person' once a title like Dr. appears)
        if entity.etype in GENERIC and etype not in GENERIC:
            entity.etype = etype
        return entity

    pair_weights: Counter[tuple[str, str]] = Counter()
    touched: set[str] = set()

    for chunk in chunks:
        found = extract_entities(chunk.text)
        entities = [upsert(name, etype) for name, etype in found]
        for entity in entities:
            db.add(EntityMention(entity_id=entity.id, chunk_id=chunk.id, document_id=doc.id))
            touched.add(entity.id)
        for a, b in combinations(sorted({e.id for e in entities}), 2):
            pair_weights[(a, b)] += 1

    for (a, b), weight in pair_weights.items():
        edge = db.scalar(select(EntityEdge).where(EntityEdge.source_id == a, EntityEdge.target_id == b))
        if edge is None:
            db.add(EntityEdge(source_id=a, target_id=b, weight=weight, doc_id=doc.id))
        else:
            edge.weight += weight

    # refresh mention counters for touched entities
    for entity_id in touched:
        entity = db.get(Entity, entity_id)
        if entity is not None:
            entity.mentions = db.query(EntityMention).filter(EntityMention.entity_id == entity_id).count()
    db.flush()
    return len(touched)


# ── queries ──────────────────────────────────────────────────────────────
def graph_data(db: Session, q: str = "", limit: int = 60) -> dict:
    stmt = select(Entity).order_by(Entity.mentions.desc())
    if q:
        stmt = stmt.where(Entity.name.ilike(f"%{q}%") | Entity.key.ilike(f"%{q.lower()}%"))
    nodes = db.scalars(stmt.limit(min(limit, 150))).all()
    ids = {n.id for n in nodes}
    edges = [
        e for e in db.scalars(select(EntityEdge).order_by(EntityEdge.weight.desc()).limit(600)).all()
        if e.source_id in ids and e.target_id in ids
    ]
    return {
        "nodes": [{"id": n.id, "name": n.name, "type": n.etype, "mentions": n.mentions} for n in nodes],
        "edges": [{"source": e.source_id, "target": e.target_id, "weight": e.weight} for e in edges],
    }


def _find_entity(db: Session, name: str) -> Entity | None:
    key = _norm(name)
    entity = db.scalar(select(Entity).where(Entity.key == key))
    if entity is None:
        entity = db.scalar(select(Entity).where(Entity.key.ilike(f"%{key}%")).order_by(Entity.mentions.desc()))
    return entity


def relate(db: Session, a: str, b: str, max_hops: int = 3) -> dict | None:
    """Shortest co-occurrence path between two entities + shared evidence."""
    ea, eb = _find_entity(db, a), _find_entity(db, b)
    if ea is None or eb is None:
        return None

    # adjacency over all edges (graph is small: capped by ingest)
    adj: dict[str, set[str]] = {}
    for e in db.scalars(select(EntityEdge)).all():
        adj.setdefault(e.source_id, set()).add(e.target_id)
        adj.setdefault(e.target_id, set()).add(e.source_id)

    # BFS
    frontier, parents, seen = [ea.id], {ea.id: None}, {ea.id}
    found = ea.id == eb.id
    for _ in range(max_hops):
        if found:
            break
        next_frontier = []
        for node in frontier:
            for nb in adj.get(node, ()):  # noqa: B023
                if nb not in seen:
                    seen.add(nb)
                    parents[nb] = node
                    next_frontier.append(nb)
                    if nb == eb.id:
                        found = True
        frontier = next_frontier

    path_ids: list[str] = []
    if found:
        cur: str | None = eb.id
        while cur is not None:
            path_ids.append(cur)
            cur = parents.get(cur)
        path_ids.reverse()

    # shared documents (co-mentioned evidence)
    docs_a = {m.document_id for m in db.scalars(select(EntityMention).where(EntityMention.entity_id == ea.id))}
    docs_b = {m.document_id for m in db.scalars(select(EntityMention).where(EntityMention.entity_id == eb.id))}
    shared = list(docs_a & docs_b)[:5]
    shared_docs = [d for doc_id in shared if (d := db.get(Document, doc_id)) is not None]

    # a couple of evidence chunks that mention either endpoint in a shared doc
    evidence: list[dict] = []
    if shared:
        rows = db.scalars(
            select(EntityMention).where(
                EntityMention.entity_id.in_([ea.id, eb.id]),
                EntityMention.document_id.in_(shared),
            ).limit(6)
        ).all()
        seen_chunks: set[str] = set()
        for m in rows:
            if m.chunk_id in seen_chunks:
                continue
            seen_chunks.add(m.chunk_id)
            chunk = db.get(Chunk, m.chunk_id)
            if chunk is not None:
                evidence.append({"doc_id": m.document_id, "text": chunk.text[:280], "section": chunk.section})
            if len(evidence) >= 3:
                break

    return {
        "a": {"id": ea.id, "name": ea.name, "type": ea.etype},
        "b": {"id": eb.id, "name": eb.name, "type": eb.etype},
        "connected": found,
        "path": [
            {"id": pid, "name": e.name, "type": e.etype}
            for pid in path_ids if (e := db.get(Entity, pid)) is not None
        ],
        "shared_documents": [{"id": d.id, "title": d.title} for d in shared_docs],
        "evidence": evidence,
    }


RELATION_RX = re.compile(
    r"\bhow (?:is|are) (.{2,60}?) (?:and|related to|connected to|linked to) (.{2,60}?)[.?]*$"
    r"|\brelationship between (.{2,60}?) and (.{2,60}?)[.?]*$",
    re.I,
)


def sensitive_names(rel: dict | None) -> list[str]:
    """PII entities touched by a graph query result — endpoints + path nodes
    whose type is sensitive (person / email / phone). Used to flag the
    granular audit log whenever an agent accesses them."""
    if not rel:
        return []
    seen: list[str] = []
    for node in [rel.get("a"), rel.get("b"), *rel.get("path", [])]:
        if node and node.get("type") in SENSITIVE_TYPES and node["name"] not in seen:
            seen.append(node["name"])
    return seen


def relational_context(db: Session, question: str) -> tuple[str, list[str]]:
    """If the question is relational ('how are X and Y related'), return a
    graph-derived context block for the Document Agent plus the list of
    sensitive (PII) entity names it touched; else ('', [])."""
    m = RELATION_RX.search(question.strip())
    if not m:
        return "", []
    trailer = re.compile(r"\s+(related|connected|linked)$", re.I)
    a = trailer.sub("", (m.group(1) or m.group(3) or "").strip())
    b = trailer.sub("", (m.group(2) or m.group(4) or "").strip())
    if not a or not b:
        return "", []
    rel = relate(db, a, b)
    if rel is None:
        return "", []
    lines = [f"KNOWLEDGE GRAPH: '{rel['a']['name']}' and '{rel['b']['name']}'"]
    if rel["connected"] and rel["path"]:
        lines.append("Connection path: " + " → ".join(p["name"] for p in rel["path"]))
    if rel["shared_documents"]:
        lines.append("Co-mentioned in: " + ", ".join(d["title"] for d in rel["shared_documents"]))
    for ev in rel["evidence"]:
        lines.append(f"Evidence: {ev['text']}")
    return "\n".join(lines), sensitive_names(rel)
