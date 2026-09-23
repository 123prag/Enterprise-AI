#!/usr/bin/env python3
"""Build the RAG vector index from data/documents/.

Usage:
    python scripts/build_rag_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.pipeline import RAGPipeline  # noqa: E402

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"


def main() -> None:
    print(f"Loading and indexing documents from {DOCS_DIR} ...")
    pipeline = RAGPipeline.build(DOCS_DIR)
    print(f"Indexed {len(pipeline.chunks)} chunks from documents in {DOCS_DIR}.")

    # Smoke query
    result = pipeline.answer("My VPN gives error 691, has this happened before?")
    print("\nSample query result:")
    print(result.answer)
    print(f"\nCitations: {[c.document_name for c in result.citations]}")


if __name__ == "__main__":
    main()
