"""Context construction and citation generation.

Turns a ranked list of retrieved chunks into (a) a single context string
suitable for handing to an LLM, with inline citation markers, and (b) a
structured citation list the caller can attach to the final answer so
every claim can be traced back to a specific document/section.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.retrieval import RetrievedChunk


@dataclass
class Citation:
    marker: str  # e.g. "[1]"
    document_id: str
    document_name: str
    section: str | None
    access_level: str


def build_context(chunks: list[RetrievedChunk], max_chars: int = 4000) -> tuple[str, list[Citation]]:
    """Build a context block and citation list, in order, truncated to
    ``max_chars`` so context size stays bounded regardless of how many
    chunks were retrieved (cost/latency control)."""
    parts: list[str] = []
    citations: list[Citation] = []
    used_chars = 0

    for i, retrieved in enumerate(chunks, start=1):
        marker = f"[{i}]"
        chunk = retrieved.chunk
        section_label = f" ({chunk.section})" if chunk.section else ""
        block = f"{marker} {chunk.document_name}{section_label}:\n{chunk.text}\n"

        if used_chars + len(block) > max_chars and parts:
            break

        parts.append(block)
        used_chars += len(block)
        citations.append(
            Citation(
                marker=marker,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                section=chunk.section,
                access_level=chunk.access_level,
            )
        )

    return "\n".join(parts), citations


def build_llm_prompt(query: str, context: str) -> str:
    """Convention consumed by DummyLLM._split_prompt: 'QUERY: ...\\n\\nCONTEXT:\\n...'."""
    return f"QUERY: {query}\n\nCONTEXT:\n{context}"


def filter_citations_by_access(citations: list[Citation], user_access_level: str) -> list[Citation]:
    """Enforce access-level filtering at the citation layer as a defense
    in depth measure (retrieval-time filtering should already have
    excluded these, but a caller that skips that filter must not leak
    restricted document names via citations either)."""
    access_rank = {"standard": 0, "elevated": 1, "restricted": 2}
    user_rank = access_rank.get(user_access_level, 0)
    return [c for c in citations if access_rank.get(c.access_level, 0) <= user_rank]
