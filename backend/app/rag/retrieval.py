"""Hybrid retrieval: dense vectors + BM25 lexical search, fused with
Reciprocal Rank Fusion (RRF). Returns citation-ready results."""
import math
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.rag.embeddings import embed_query
from app.rag.vectorstore import get_vectorstore

TOKEN = re.compile(r"[a-z0-9]+")
MAX_CORPUS = 5000  # BM25 corpus cap — swap for a search service beyond this scale
RRF_K = 60


@dataclass
class Retrieved:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    page: int
    text: str
    score: float


def hybrid_search(db: Session, query: str, k: int = 6) -> list[Retrieved]:
    rows = db.execute(
        select(Chunk.id, Chunk.document_id, Chunk.text, Chunk.section, Chunk.page).limit(MAX_CORPUS)
    ).all()
    if not rows:
        return []

    by_id = {r[0]: r for r in rows}

    lexical_rank = _bm25_rank(query, rows)                       # [chunk_id] best-first
    vector_rank = [
        hit_id for hit_id, _score, _payload in get_vectorstore().search(embed_query(query), k=k * 3)
        if hit_id in by_id
    ]

    # Reciprocal Rank Fusion
    fused: dict[str, float] = {}
    for rank_list in (lexical_rank, vector_rank):
        for rank, chunk_id in enumerate(rank_list):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

    top = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:k]
    if not top:
        return []

    titles = dict(db.execute(select(Document.id, Document.title)).all())
    max_score = top[0][1]
    return [
        Retrieved(
            chunk_id=cid,
            doc_id=by_id[cid][1],
            title=titles.get(by_id[cid][1], "Unknown document"),
            section=by_id[cid][3] or "",
            page=by_id[cid][4] or 0,
            text=by_id[cid][2],
            score=round(score / max_score, 3),  # normalized 0-1
        )
        for cid, score in top
    ]


def _bm25_rank(query: str, rows: list, k1: float = 1.5, b: float = 0.75) -> list[str]:
    corpus = {r[0]: TOKEN.findall(r[2].lower()) for r in rows}
    n_docs = len(corpus)
    avg_len = sum(len(t) for t in corpus.values()) / max(n_docs, 1)

    document_freq: dict[str, int] = {}
    for tokens in corpus.values():
        for term in set(tokens):
            document_freq[term] = document_freq.get(term, 0) + 1

    query_terms = TOKEN.findall(query.lower())
    scores: dict[str, float] = {}
    for chunk_id, tokens in corpus.items():
        if not tokens:
            continue
        term_freq: dict[str, int] = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
        score = 0.0
        for term in query_terms:
            if term not in term_freq:
                continue
            df = document_freq.get(term, 0)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            tf = term_freq[term]
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(tokens) / avg_len))
        if score > 0:
            scores[chunk_id] = score

    return [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
