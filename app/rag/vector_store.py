"""Vector store abstraction: FAISS for local development, Qdrant for
production, selected via ``settings.vector_store_provider``.

The FAISS backend degrades gracefully to a pure-NumPy brute-force cosine
index if the ``faiss`` package is not installed, so local development and
CI never hard-fail just because the (fairly heavy) faiss-cpu wheel isn't
present — it's a drop-in swap, not a different interface.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict


@dataclass
class VectorMatch:
    id: str
    score: float
    payload: dict


class BaseVectorStore(ABC):
    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[VectorMatch]: ...

    @abstractmethod
    def count(self) -> int: ...


class NumpyBruteForceStore(BaseVectorStore):
    """Pure-NumPy cosine-similarity index. No external dependency.

    Used automatically when ``faiss`` isn't installed, and always
    sufficient at this project's data scale (hundreds of chunks).
    """

    def __init__(self):
        self._ids: list[str] = []
        self._vectors: np.ndarray | None = None
        self._payloads: list[dict] = []

    def upsert(self, records: list[VectorRecord]) -> None:
        vecs = np.array([r.vector for r in records], dtype=np.float32)
        if self._vectors is None:
            self._vectors = vecs
        else:
            self._vectors = np.vstack([self._vectors, vecs])
        self._ids.extend(r.id for r in records)
        self._payloads.extend(r.payload for r in records)

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[VectorMatch]:
        if self._vectors is None or len(self._ids) == 0:
            return []
        sims = self._vectors @ query_vector  # vectors are pre-normalized
        top_idx = np.argsort(-sims)[:top_k]
        return [
            VectorMatch(id=self._ids[i], score=float(sims[i]), payload=self._payloads[i])
            for i in top_idx
        ]

    def count(self) -> int:
        return len(self._ids)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if self._vectors is not None:
            np.save(directory / "vectors.npy", self._vectors)
        (directory / "meta.json").write_text(
            json.dumps({"ids": self._ids, "payloads": self._payloads})
        )

    @classmethod
    def load(cls, directory: Path) -> "NumpyBruteForceStore":
        store = cls()
        meta_path = directory / "meta.json"
        vec_path = directory / "vectors.npy"
        if meta_path.exists() and vec_path.exists():
            meta = json.loads(meta_path.read_text())
            store._ids = meta["ids"]
            store._payloads = meta["payloads"]
            store._vectors = np.load(vec_path)
        return store


class FaissVectorStore(BaseVectorStore):
    """FAISS-backed store; falls back to :class:`NumpyBruteForceStore`
    transparently if faiss is not importable in this environment."""

    def __init__(self, dim: int, index_dir: str):
        self.dim = dim
        self.index_dir = Path(index_dir)
        self._payloads: list[dict] = []
        self._ids: list[str] = []
        try:
            import faiss  # noqa: F401

            self._faiss_available = True
            self._index = faiss.IndexFlatIP(dim)
        except ImportError:
            logger.warning(
                "faiss not installed; falling back to NumPy brute-force "
                "vector search (fine at this project's data scale)."
            )
            self._faiss_available = False
            self._fallback = NumpyBruteForceStore()

    def upsert(self, records: list[VectorRecord]) -> None:
        if not self._faiss_available:
            self._fallback.upsert(records)
            return
        import faiss  # noqa: F401

        vecs = np.array([r.vector for r in records], dtype=np.float32)
        self._index.add(vecs)
        self._ids.extend(r.id for r in records)
        self._payloads.extend(r.payload for r in records)

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[VectorMatch]:
        if not self._faiss_available:
            return self._fallback.search(query_vector, top_k)
        if self._index.ntotal == 0:
            return []
        scores, idxs = self._index.search(query_vector.reshape(1, -1), top_k)
        matches = []
        for score, idx in zip(scores[0], idxs[0], strict=True):
            if idx == -1:
                continue
            matches.append(
                VectorMatch(id=self._ids[idx], score=float(score), payload=self._payloads[idx])
            )
        return matches

    def count(self) -> int:
        if not self._faiss_available:
            return self._fallback.count()
        return self._index.ntotal


class QdrantVectorStore(BaseVectorStore):
    """Production vector store backed by Qdrant. Requires a reachable
    Qdrant instance (see docker-compose.yml in later phases)."""

    COLLECTION = "incident_kb"

    def __init__(self, dim: int, url: str, api_key: str = ""):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.client = QdrantClient(url=url, api_key=api_key or None)
        self.dim = dim
        existing = [c.name for c in self.client.get_collections().collections]
        if self.COLLECTION not in existing:
            self.client.create_collection(
                collection_name=self.COLLECTION,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, records: list[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=abs(hash(r.id)) % (2**63), vector=r.vector, payload={**r.payload, "_id": r.id})
            for r in records
        ]
        self.client.upsert(collection_name=self.COLLECTION, points=points)

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[VectorMatch]:
        results = self.client.search(
            collection_name=self.COLLECTION,
            query_vector=query_vector.tolist(),
            limit=top_k,
        )
        return [
            VectorMatch(id=r.payload.get("_id", str(r.id)), score=r.score, payload=r.payload)
            for r in results
        ]

    def count(self) -> int:
        return self.client.count(collection_name=self.COLLECTION).count


def get_vector_store(dim: int) -> BaseVectorStore:
    settings = get_settings()
    if settings.vector_store_provider == "qdrant":
        return QdrantVectorStore(dim, settings.qdrant_url, settings.qdrant_api_key)
    return FaissVectorStore(dim, settings.faiss_index_dir)
