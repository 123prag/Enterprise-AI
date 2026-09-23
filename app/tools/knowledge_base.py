"""search_knowledge_base tool: thin typed wrapper around the RAG pipeline
built in Phase 3.

The pipeline is expensive to build (loads + chunks + embeds all
documents), so it's constructed once per process and cached.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.rag.pipeline import RAGPipeline
from app.rag.retrieval import MetadataFilter
from app.tools.schemas import ToolOutput

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "documents"


@lru_cache(maxsize=1)
def _get_pipeline() -> RAGPipeline:
    return RAGPipeline.build(DOCS_DIR)


class SearchKnowledgeBaseInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    department: str | None = None
    document_type: str | None = None
    user_access_level: str = "standard"


class CitationOut(BaseModel):
    marker: str
    document_id: str
    document_name: str
    section: str | None


class SearchKnowledgeBaseOutput(ToolOutput):
    answer: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    retrieved_count: int = 0


def search_knowledge_base(input: SearchKnowledgeBaseInput) -> SearchKnowledgeBaseOutput:
    try:
        pipeline = _get_pipeline()
        metadata_filter = None
        if input.department or input.document_type:
            metadata_filter = MetadataFilter(
                department=input.department, document_type=input.document_type
            )

        result = pipeline.answer(
            input.query,
            top_k=input.top_k,
            metadata_filter=metadata_filter,
            user_access_level=input.user_access_level,
        )

        return SearchKnowledgeBaseOutput(
            answer=result.answer,
            citations=[
                CitationOut(
                    marker=c.marker,
                    document_id=c.document_id,
                    document_name=c.document_name,
                    section=c.section,
                )
                for c in result.citations
            ],
            retrieved_count=result.retrieved_count,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("search_knowledge_base error")
        return SearchKnowledgeBaseOutput(success=False, error=str(e))
