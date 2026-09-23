"""Phase 3 tests: ingestion, chunking, embeddings, hybrid retrieval,
reranking, citations, and the end-to-end pipeline against the real
synthetic documents in data/documents/.
"""

from pathlib import Path

import numpy as np

from app.rag.chunking import chunk_document, chunk_documents
from app.rag.citations import build_context, filter_citations_by_access
from app.rag.embeddings import DummyHashingEmbedder
from app.rag.ingestion import load_document, load_documents_from_dir
from app.rag.pipeline import RAGPipeline
from app.rag.reranking import LexicalOverlapReranker
from app.rag.retrieval import HybridRetriever, MetadataFilter
from app.rag.vector_store import NumpyBruteForceStore, VectorRecord

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"


def test_load_all_documents_parses_frontmatter():
    docs = load_documents_from_dir(DOCS_DIR)
    assert len(docs) == 15
    vpn_doc = next(d for d in docs if d.document_id == "vpn_troubleshooting_sop")
    assert vpn_doc.document_type == "sop"
    assert vpn_doc.department == "IT Operations"
    assert "691" in vpn_doc.text


def test_chunking_preserves_section_titles():
    doc = load_document(DOCS_DIR / "vpn_troubleshooting_sop.md")
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    sections = {c.section for c in chunks}
    assert any(s and "691" in s for s in sections)
    # every chunk carries the full metadata contract
    for c in chunks:
        assert c.document_id and c.document_name and c.document_type
        assert c.access_level == "standard"


def test_dummy_embedder_is_deterministic_and_similarity_aware():
    embedder = DummyHashingEmbedder(dim=64)
    v1 = embedder.embed_one("VPN error 691 authentication failed")
    v2 = embedder.embed_one("VPN error 691 authentication failed")
    assert np.allclose(v1, v2)

    v3 = embedder.embed_one("VPN error 691 authentication rejected")
    v4 = embedder.embed_one("completely unrelated lunch menu options")

    sim_related = float(v1 @ v3)
    sim_unrelated = float(v1 @ v4)
    assert sim_related > sim_unrelated


def test_numpy_vector_store_returns_nearest_neighbors():
    store = NumpyBruteForceStore()
    embedder = DummyHashingEmbedder(dim=64)
    texts = ["VPN error 691 authentication issue", "password reset email guide", "office lunch menu"]
    vecs = embedder.embed(texts)
    store.upsert(
        [VectorRecord(id=f"c{i}", vector=vecs[i].tolist(), payload={}) for i in range(len(texts))]
    )
    query_vec = embedder.embed_one("VPN authentication error")
    matches = store.search(query_vec, top_k=1)
    assert matches[0].id == "c0"


def test_hybrid_retrieval_surfaces_relevant_vpn_chunk():
    docs = load_documents_from_dir(DOCS_DIR)
    chunks = chunk_documents(docs)

    embedder = DummyHashingEmbedder(dim=128)
    vectors = embedder.embed([c.text for c in chunks])
    store = NumpyBruteForceStore()
    store.upsert(
        [
            VectorRecord(id=c.chunk_id, vector=vectors[i].tolist(), payload={})
            for i, c in enumerate(chunks)
        ]
    )
    retriever = HybridRetriever(
        chunks=chunks,
        vector_store=store,
        embedder=embedder,
        chunk_ids_in_store_order=[c.chunk_id for c in chunks],
    )

    results = retriever.retrieve("VPN error 691 after Windows update", top_k=5)
    assert len(results) > 0
    top_doc_ids = {r.chunk.document_id for r in results}
    assert "vpn_troubleshooting_sop" in top_doc_ids or "vpn_error_code_reference" in top_doc_ids


def test_metadata_filter_excludes_non_matching_department():
    docs = load_documents_from_dir(DOCS_DIR)
    chunks = chunk_documents(docs)
    embedder = DummyHashingEmbedder(dim=64)
    vectors = embedder.embed([c.text for c in chunks])
    store = NumpyBruteForceStore()
    store.upsert(
        [
            VectorRecord(id=c.chunk_id, vector=vectors[i].tolist(), payload={})
            for i, c in enumerate(chunks)
        ]
    )
    retriever = HybridRetriever(
        chunks=chunks,
        vector_store=store,
        embedder=embedder,
        chunk_ids_in_store_order=[c.chunk_id for c in chunks],
    )

    results = retriever.retrieve(
        "VPN error",
        top_k=10,
        metadata_filter=MetadataFilter(department="Security"),
    )
    assert all(r.chunk.department == "Security" for r in results)


def test_reranker_prioritizes_query_term_coverage():
    docs = load_documents_from_dir(DOCS_DIR)
    chunks = chunk_documents(docs)
    embedder = DummyHashingEmbedder(dim=64)
    vectors = embedder.embed([c.text for c in chunks])
    store = NumpyBruteForceStore()
    store.upsert(
        [
            VectorRecord(id=c.chunk_id, vector=vectors[i].tolist(), payload={})
            for i, c in enumerate(chunks)
        ]
    )
    retriever = HybridRetriever(
        chunks=chunks,
        vector_store=store,
        embedder=embedder,
        chunk_ids_in_store_order=[c.chunk_id for c in chunks],
    )
    candidates = retriever.retrieve("MFA push notifications not arriving", top_k=10)
    reranker = LexicalOverlapReranker()
    reranked = reranker.rerank("MFA push notifications not arriving", candidates)
    assert reranked
    assert "mfa" in reranked[0].chunk.text.lower() or "push" in reranked[0].chunk.text.lower()


def test_build_context_produces_numbered_citations():
    docs = load_documents_from_dir(DOCS_DIR)
    chunks = chunk_documents(docs)
    embedder = DummyHashingEmbedder(dim=64)
    vectors = embedder.embed([c.text for c in chunks])
    store = NumpyBruteForceStore()
    store.upsert(
        [
            VectorRecord(id=c.chunk_id, vector=vectors[i].tolist(), payload={})
            for i, c in enumerate(chunks)
        ]
    )
    retriever = HybridRetriever(
        chunks=chunks,
        vector_store=store,
        embedder=embedder,
        chunk_ids_in_store_order=[c.chunk_id for c in chunks],
    )
    results = retriever.retrieve("VPN error 691", top_k=3)
    context, citations = build_context(results)
    assert "[1]" in context
    assert len(citations) == len(results)
    assert citations[0].marker == "[1]"


def test_access_level_filtering():
    from app.rag.citations import Citation

    citations = [
        Citation(marker="[1]", document_id="d1", document_name="Doc1", section=None, access_level="standard"),
        Citation(marker="[2]", document_id="d2", document_name="Doc2", section=None, access_level="restricted"),
    ]
    filtered = filter_citations_by_access(citations, user_access_level="standard")
    assert len(filtered) == 1
    assert filtered[0].document_id == "d1"


def test_end_to_end_pipeline_answers_with_citations():
    pipeline = RAGPipeline.build(DOCS_DIR)
    result = pipeline.answer("My VPN gives error 691 after a Windows update, has this happened before?")
    assert result.retrieved_count > 0
    assert len(result.citations) > 0
    assert result.answer  # dummy LLM should produce a non-empty extractive answer
    assert result.input_tokens > 0
