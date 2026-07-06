"""Vector store abstraction: Qdrant in production, persistent in-memory fallback in dev."""
import json
import logging
import math
import os
import threading

from app.core.config import settings

log = logging.getLogger("eaios.vectors")
COLLECTION = "eaios_chunks"


class MemoryVectorStore:
    """Cosine-similarity store persisted to disk as JSON. Fine for dev/demo scale."""

    backend_name = "in-memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._path = os.path.join(settings.UPLOAD_DIR, ".vectors.json")
        self._items: dict[str, dict] = {}
        self._load()

    def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        with self._lock:
            for id_, vec, payload in zip(ids, vectors, payloads):
                self._items[id_] = {"v": vec, "p": payload}
            self._save()

    def search(self, vector: list[float], k: int = 8) -> list[tuple[str, float, dict]]:
        scored = [
            (id_, _cosine(vector, item["v"]), item["p"])
            for id_, item in self._items.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            self._items = {i: it for i, it in self._items.items() if it["p"].get("doc_id") != doc_id}
            self._save()

    def _save(self) -> None:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._items, f)

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    self._items = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._items = {}


class QdrantVectorStore:
    backend_name = "qdrant"

    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.client = QdrantClient(url=settings.QDRANT_URL, timeout=10)
        existing = {c.name for c in self.client.get_collections().collections}
        if COLLECTION not in existing:
            self.client.create_collection(
                COLLECTION,
                vectors_config=VectorParams(size=settings.EMBEDDING_DIM, distance=Distance.COSINE),
            )

    def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=_uuid_from(id_), vector=vec, payload={**payload, "chunk_id": id_})
            for id_, vec, payload in zip(ids, vectors, payloads)
        ]
        self.client.upsert(COLLECTION, points=points)

    def search(self, vector: list[float], k: int = 8) -> list[tuple[str, float, dict]]:
        hits = self.client.search(COLLECTION, query_vector=vector, limit=k)
        return [(h.payload.get("chunk_id", str(h.id)), float(h.score), dict(h.payload)) for h in hits]

    def delete_document(self, doc_id: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        self.client.delete(
            COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
            ),
        )


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def _uuid_from(chunk_id: str) -> str:
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_OID, chunk_id))


_store = None
_store_lock = threading.Lock()


def get_vectorstore():
    global _store
    with _store_lock:
        if _store is None:
            if settings.QDRANT_URL:
                try:
                    _store = QdrantVectorStore()
                    log.info("Vector store: Qdrant @ %s", settings.QDRANT_URL)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Qdrant unavailable (%s) — using in-memory store", exc)
                    _store = MemoryVectorStore()
            else:
                _store = MemoryVectorStore()
        return _store
