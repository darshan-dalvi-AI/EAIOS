"""Automated RAG retrieval evaluation — a lightweight Ragas-style regression
gate that runs in CI (plain pytest, zero extra deps).

Retrieval quality is the foundation of every grounded answer, so we assert it
never silently degrades. Over a hand-written Q/A set keyed to the seed corpus,
we measure:

- **Hit-rate@k** — did the correct source document appear in the top-k chunks?
- **MRR** — mean reciprocal rank of the correct document (how high it ranked).

Thresholds are conservative enough to be stable but high enough that a real
regression in chunking, embeddings or fusion fails the build.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.mkdtemp(prefix="eaios_rageval_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'eval.db')}")
os.environ.setdefault("UPLOAD_DIR", os.path.join(_TMP, "uploads"))
os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest  # noqa: E402

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.rag.retrieval import hybrid_search  # noqa: E402

# (question, expected source-document title) — titles come from seed.py filenames
EVAL_SET: list[tuple[str, str]] = [
    ("How many annual leave days do employees get?", "HR Leave Policy"),
    ("Can I carry forward unused leave to next year?", "HR Leave Policy"),
    ("What was Q3 revenue and how much did it grow?", "Q3 Financial Summary"),
    ("How much did the Enterprise segment contribute?", "Q3 Financial Summary"),
    ("What are the minimum hardware requirements for Atlas?", "Atlas Product Manual"),
    ("What roles does the Atlas platform define?", "Atlas Product Manual"),
    ("Who do I contact for a security incident?", "Security Incident SOP"),
    ("When must legal be looped into an incident?", "Security Incident SOP"),
]

K = 6
MIN_HIT_RATE = 0.75   # ≥ 6/8 questions retrieve the right document in top-6
MIN_MRR = 0.55


@pytest.fixture(scope="module")
def seeded_db():
    init_db()
    from app.seed import seed

    seed()  # idempotent
    with SessionLocal() as db:
        yield db


def test_retrieval_quality(seeded_db):
    db = seeded_db
    hits, reciprocal_ranks, misses = 0, [], []

    for question, expected_title in EVAL_SET:
        results = hybrid_search(db, question, k=K)
        titles = [r.title for r in results]
        if expected_title in titles:
            hits += 1
            reciprocal_ranks.append(1.0 / (titles.index(expected_title) + 1))
        else:
            reciprocal_ranks.append(0.0)
            misses.append(f"{question!r} → expected {expected_title!r}, got {titles[:3]}")

    hit_rate = hits / len(EVAL_SET)
    mrr = sum(reciprocal_ranks) / len(EVAL_SET)
    print(f"\nRAG eval — hit-rate@{K}={hit_rate:.0%}  MRR={mrr:.2f}  ({hits}/{len(EVAL_SET)})")
    for m in misses:
        print("  MISS:", m)

    assert hit_rate >= MIN_HIT_RATE, f"retrieval hit-rate {hit_rate:.0%} < {MIN_HIT_RATE:.0%}"
    assert mrr >= MIN_MRR, f"retrieval MRR {mrr:.2f} < {MIN_MRR}"


def test_no_cross_document_contamination(seeded_db):
    """A leave-policy question must not rank a financial doc as #1."""
    results = hybrid_search(seeded_db, "How many paid annual leave days do we get?", k=K)
    assert results, "no results returned"
    assert results[0].title == "HR Leave Policy", f"top hit was {results[0].title!r}"
