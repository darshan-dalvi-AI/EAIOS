"""Embedding providers behind one function.

- hash  : zero-dependency feature-hashing embeddings (deterministic, dev/demo)
- ollama: nomic-embed-text or similar via local Ollama
- sentence-transformers: real dense embeddings (BGE / MiniLM) when installed

Cosine similarity over hash embeddings correlates with token overlap, which is
enough to demonstrate the full retrieval pipeline without model downloads."""
import hashlib
import math
import re

from app.core.config import settings

TOKEN = re.compile(r"[a-z0-9]+")


_resolved: str | None = None


def _resolve() -> str:
    global _resolved
    if _resolved is None:
        p = settings.EMBEDDING_PROVIDER.lower()
        if p == "auto":
            try:
                from app.llm.provider import ollama_tags

                p = "ollama" if any(t.startswith("nomic-embed") for t in ollama_tags()) else "hash"
            except Exception:
                p = "hash"
        _resolved = p
    return _resolved


def embed_texts(texts: list[str]) -> list[list[float]]:
    provider = _resolve()
    if provider == "ollama":
        try:
            return _ollama(texts)
        except Exception:
            pass  # fall back to hash so ingestion never hard-fails in dev
    if provider == "sentence-transformers":
        try:
            return _sentence_transformers(texts)
        except ImportError:
            pass
    return [_hash_embed(t) for t in texts]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


# ── hash embeddings ──────────────────────────────────────────────

def _hash_embed(text: str, dim: int | None = None) -> list[float]:
    dim = dim or settings.EMBEDDING_DIM
    vec = [0.0] * dim
    tokens = TOKEN.findall(text.lower())
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    for gram in grams:
        digest = hashlib.md5(gram.encode()).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


# ── real providers ───────────────────────────────────────────────

def _ollama(texts: list[str]) -> list[list[float]]:
    import httpx

    out: list[list[float]] = []
    with httpx.Client(base_url=settings.OLLAMA_BASE_URL, timeout=30, trust_env=False) as client:
        for text in texts:
            r = client.post("/api/embeddings", json={"model": "nomic-embed-text", "prompt": text})
            r.raise_for_status()
            out.append(r.json()["embedding"])
    return out


_st_model = None


def _sentence_transformers(texts: list[str]) -> list[list[float]]:
    global _st_model
    from sentence_transformers import SentenceTransformer

    if _st_model is None:
        _st_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return [list(map(float, v)) for v in _st_model.encode(texts, normalize_embeddings=True)]
