"""Top-level RAG pipeline: wires ingestion -> chunking -> embeddings ->
vector store (build time), and retrieval -> reranking -> context ->
LLM -> citations (query time).

Build the index once (or whenever documents change):

    from app.rag.pipeline import RAGPipeline
    pipeline = RAGPipeline.build(Path("data/documents"))

Then answer queries:

    result = pipeline.answer("My VPN gives error 691, has this happened before?")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.llm.provider import BaseLLM, get_llm
from app.rag.chunking import Chunk, chunk_documents
from app.rag.citations import Citation, build_context, build_llm_prompt
from app.rag.embeddings import BaseEmbedder, get_embedder
from app.rag.ingestion import load_documents_from_dir
from app.rag.reranking import BaseReranker, get_reranker
from app.rag.retrieval import HybridRetriever, MetadataFilter
from app.rag.vector_store import VectorRecord, get_vector_store


@dataclass
class RAGAnswer:
    answer: str
    citations: list[Citation]
    context_used: str
    retrieved_count: int
    input_tokens: int
    output_tokens: int


class RAGPipeline:
    def __init__(
        self,
        chunks: list[Chunk],
        retriever: HybridRetriever,
        reranker: BaseReranker,
        llm: BaseLLM,
    ):
        self.chunks = chunks
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm

    @classmethod
    def build(cls, documents_dir: Path) -> "RAGPipeline":
        docs = load_documents_from_dir(documents_dir)
        chunks = chunk_documents(docs)

        embedder: BaseEmbedder = get_embedder()
        vectors = embedder.embed([c.text for c in chunks])

        vector_store = get_vector_store(dim=embedder.dim)
        chunk_order = [c.chunk_id for c in chunks]
        vector_store.upsert(
            [
                VectorRecord(
                    id=chunk.chunk_id,
                    vector=vectors[i].tolist(),
                    payload={
                        "document_id": chunk.document_id,
                        "document_name": chunk.document_name,
                        "document_type": chunk.document_type,
                        "department": chunk.department,
                        "section": chunk.section,
                        "access_level": chunk.access_level,
                    },
                )
                for i, chunk in enumerate(chunks)
            ]
        )

        retriever = HybridRetriever(
            chunks=chunks,
            vector_store=vector_store,
            embedder=embedder,
            chunk_ids_in_store_order=chunk_order,
        )

        return cls(chunks=chunks, retriever=retriever, reranker=get_reranker(), llm=get_llm())

    def answer(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: MetadataFilter | None = None,
        user_access_level: str = "standard",
    ) -> RAGAnswer:
        candidates = self.retriever.retrieve(
            query, top_k=max(top_k * 3, 10), metadata_filter=metadata_filter
        )
        reranked = self.reranker.rerank(query, candidates)[:top_k]

        context, citations = build_context(reranked)

        from app.rag.citations import filter_citations_by_access

        citations = filter_citations_by_access(citations, user_access_level)

        if not reranked:
            return RAGAnswer(
                answer=(
                    "No relevant documentation was found for this query. "
                    "It may require escalation or fall outside the current "
                    "knowledge base."
                ),
                citations=[],
                context_used="",
                retrieved_count=0,
                input_tokens=0,
                output_tokens=0,
            )

        prompt = build_llm_prompt(query, context)
        response = self.llm.complete(
            system=(
                "You are an enterprise IT knowledge assistant. Answer only "
                "using the provided context. Cite sources using the [n] "
                "markers given. If the context does not support an answer, "
                "say so explicitly rather than guessing."
            ),
            user=prompt,
        )

        return RAGAnswer(
            answer=response.text,
            citations=citations,
            context_used=context,
            retrieved_count=len(reranked),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
