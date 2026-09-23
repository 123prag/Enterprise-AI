"""Reranking: a second-pass relevance scorer applied to the (small) set of
hybrid-retrieval candidates before context construction.

The default reranker is a lexical one (query-term coverage + position
bonus) — deliberately simple and dependency-free so it runs identically
offline and in production. A real cross-encoder reranker can be dropped
in behind the same interface (``BaseReranker.rerank``) without touching
callers; this project does not fabricate benchmark numbers for a
cross-encoder it cannot actually run in the local/offline mode.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from app.rag.retrieval import RetrievedChunk


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class LexicalOverlapReranker(BaseReranker):
    """Scores each candidate by fraction of query terms present in the
    chunk text, with a small bonus for terms appearing early (titles/
    section headers tend to be most informative) and blends in the
    original fused retrieval score so reranking refines rather than
    discards the hybrid signal.
    """

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        query_terms = set(_tokenize(query))
        if not query_terms:
            return candidates

        scored = []
        for cand in candidates:
            chunk_terms = _tokenize(cand.chunk.text)
            chunk_term_set = set(chunk_terms)
            coverage = len(query_terms & chunk_term_set) / len(query_terms)

            # position bonus: does a query term appear in the first 15 tokens?
            head_terms = set(chunk_terms[:15])
            position_bonus = 0.1 if (query_terms & head_terms) else 0.0

            section_bonus = 0.0
            if cand.chunk.section:
                section_terms = set(_tokenize(cand.chunk.section))
                if query_terms & section_terms:
                    section_bonus = 0.15

            rerank_score = (
                0.6 * coverage
                + 0.2 * cand.fused_score
                + position_bonus
                + section_bonus
            )
            scored.append((rerank_score, cand))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]


def get_reranker() -> BaseReranker:
    return LexicalOverlapReranker()
