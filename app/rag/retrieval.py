"""Hybrid retrieval: combines BM25 (keyword) and vector (semantic) search
via reciprocal rank fusion, with metadata filtering applied before fusion
so filtered-out chunks never influence scores.

This is the retrieval layer the RAG agent calls; reranking (a separate,
later step) operates on this layer's output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.chunking import Chunk
from app.rag.embeddings import BaseEmbedder
from app.rag.vector_store import BaseVectorStore

try:
    from rank_bm25 import BM25Okapi

    _BM25_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the dep installed
    _BM25_AVAILABLE = False


@dataclass
class RetrievedChunk:
    chunk: Chunk
    vector_score: float
    bm25_score: float
    fused_score: float


@dataclass
class MetadataFilter:
    document_type: str | None = None
    department: str | None = None
    access_level: str | None = None

    def matches(self, chunk: Chunk) -> bool:
        if self.document_type and chunk.document_type != self.document_type:
            return False
        if self.department and chunk.department != self.department:
            return False
        if self.access_level and chunk.access_level != self.access_level:
            return False
        return True


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class SimpleBM25Fallback:
    """Minimal TF-based scorer used only if rank_bm25 isn't installed."""

    def __init__(self, corpus_tokens: list[list[str]]):
        self.corpus_tokens = corpus_tokens

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores = []
        for doc_tokens in self.corpus_tokens:
            doc_set = set(doc_tokens)
            scores.append(float(sum(1 for t in query_tokens if t in doc_set)))
        return scores


class HybridRetriever:
    def __init__(
        self,
        chunks: list[Chunk],
        vector_store: BaseVectorStore,
        embedder: BaseEmbedder,
        chunk_ids_in_store_order: list[str],
    ):
        """``chunk_ids_in_store_order`` must match the order chunks were
        upserted into ``vector_store`` (used to align BM25 corpus index ->
        chunk, since BM25 runs independently of the vector store)."""
        self.chunks_by_id = {c.chunk_id: c for c in chunks}
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunk_order = chunk_ids_in_store_order

        tokenized = [_tokenize(self.chunks_by_id[cid].text) for cid in self.chunk_order]
        self._bm25 = (
            BM25Okapi(tokenized) if _BM25_AVAILABLE else SimpleBM25Fallback(tokenized)
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: MetadataFilter | None = None,
        vector_candidates: int = 20,
    ) -> list[RetrievedChunk]:
        query_vec = self.embedder.embed_one(query)
        vector_matches = self.vector_store.search(query_vec, top_k=vector_candidates)
        vector_scores = {m.id: m.score for m in vector_matches}

        query_tokens = _tokenize(query)
        bm25_scores_raw = self._bm25.get_scores(query_tokens)
        bm25_scores = dict(zip(self.chunk_order, bm25_scores_raw, strict=True))

        # Reciprocal rank fusion over the union of candidates from both signals
        candidate_ids = set(vector_scores) | {
            cid for cid, s in bm25_scores.items() if s > 0
        }

        vector_rank = {
            cid: rank
            for rank, cid in enumerate(
                sorted(vector_scores, key=lambda c: -vector_scores[c])
            )
        }
        bm25_rank = {
            cid: rank
            for rank, cid in enumerate(
                sorted(bm25_scores, key=lambda c: -bm25_scores[c])
            )
        }

        k = 60  # standard RRF constant
        results: list[RetrievedChunk] = []
        for cid in candidate_ids:
            chunk = self.chunks_by_id.get(cid)
            if chunk is None:
                continue
            if metadata_filter and not metadata_filter.matches(chunk):
                continue
            rrf = 0.0
            if cid in vector_rank:
                rrf += 1.0 / (k + vector_rank[cid])
            if cid in bm25_rank:
                rrf += 1.0 / (k + bm25_rank[cid])
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    vector_score=vector_scores.get(cid, 0.0),
                    bm25_score=bm25_scores.get(cid, 0.0),
                    fused_score=rrf,
                )
            )

        results.sort(key=lambda r: r.fused_score, reverse=True)
        return results[:top_k]
