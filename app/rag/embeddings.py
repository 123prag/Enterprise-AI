"""Embedding provider abstraction.

Like the LLM abstraction, nothing outside this module should call an
embedding API directly. ``EMBEDDING_PROVIDER=dummy`` (the local-mode
default) uses a deterministic hashing-trick embedder: no network, no
model download, no API key, and — importantly — genuinely sensitive to
word overlap, so cosine similarity between the hashed vectors is a
meaningful (if crude) relevance signal for tests and local development.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

import numpy as np

from app.config import get_settings

DUMMY_EMBEDDING_DIM = 256


class BaseEmbedder(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array, L2-normalized per row."""
        ...

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class DummyHashingEmbedder(BaseEmbedder):
    """Deterministic offline embedder using the hashing trick.

    Each token is hashed into one of ``dim`` buckets (sign determined by a
    second hash, à la feature hashing for signed count sketches), the
    bucket vector is L2-normalized. Identical text always produces an
    identical vector, and texts sharing vocabulary produce vectors with
    positive cosine similarity — enough signal for meaningful nearest-
    neighbor retrieval in tests and offline development, without needing
    any ML model.
    """

    def __init__(self, dim: int = DUMMY_EMBEDDING_DIM):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in _tokenize(text):
                h = hashlib.sha256(token.encode("utf-8")).hexdigest()
                bucket = int(h[:8], 16) % self.dim
                sign = 1.0 if int(h[8:9], 16) % 2 == 0 else -1.0
                vectors[i, bucket] += sign
            norm = np.linalg.norm(vectors[i])
            if norm > 0:
                vectors[i] /= norm
        return vectors


class OpenAIEmbedder(BaseEmbedder):
    """Real OpenAI embeddings. Requires network + EMBEDDING_API_KEY."""

    def __init__(self, model: str, api_key: str, dim: int = 1536):
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai requires EMBEDDING_API_KEY to be set in .env"
            )
        self.model = model
        self.api_key = api_key
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        import httpx

        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        vecs = np.array([item["embedding"] for item in data["data"]], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms


class SentenceTransformerEmbedder(BaseEmbedder):
    """Real local embedding model via sentence-transformers.

    Requires the `sentence-transformers` package and a downloaded model —
    not installed by default (heavy dependency), so this raises a clear
    error unless the package is available.
    """

    def __init__(self, model: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=sentence-transformers requires the "
                "'sentence-transformers' package (not in requirements.txt "
                "by default due to size). Install it explicitly to use "
                "this provider."
            ) from e
        self._model = SentenceTransformer(model)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)


def get_embedder() -> BaseEmbedder:
    settings = get_settings()
    if settings.embedding_provider == "dummy":
        return DummyHashingEmbedder()
    if settings.embedding_provider == "openai":
        return OpenAIEmbedder(settings.embedding_model, settings.embedding_api_key)
    if settings.embedding_provider == "sentence-transformers":
        return SentenceTransformerEmbedder(settings.embedding_model)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")
