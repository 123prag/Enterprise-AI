"""Section-aware chunking.

Splits a document's body on Markdown headers first (so a chunk never
straddles two unrelated sections), then further splits any section that
is still too long into overlapping fixed-size windows. Each resulting
chunk carries the full metadata contract required by the project spec:
document_id, document_name, document_type, department, version, section,
created_at, access_level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.rag.ingestion import RawDocument

DEFAULT_CHUNK_SIZE = 800  # characters
DEFAULT_CHUNK_OVERLAP = 120


@dataclass
class Chunk:
    chunk_id: str
    text: str
    document_id: str
    document_name: str
    document_type: str
    department: str | None
    version: str
    section: str | None
    created_at: datetime
    access_level: str


def _split_by_headers(text: str) -> list[tuple[str | None, str]]:
    """Return [(section_title, section_text), ...]. Text before the first
    header (if any) gets section_title=None."""
    pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return [(None, text)]

    sections: list[tuple[str | None, str]] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append((None, preamble))

    for i, m in enumerate(matches):
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    return sections


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    windows = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        windows.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return windows


def chunk_document(
    doc: RawDocument,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    sections = _split_by_headers(doc.text)

    for section_idx, (section_title, section_text) in enumerate(sections):
        windows = _sliding_window(section_text, chunk_size, overlap)
        for window_idx, window_text in enumerate(windows):
            chunk_id = f"{doc.document_id}::s{section_idx}::c{window_idx}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=window_text.strip(),
                    document_id=doc.document_id,
                    document_name=doc.document_name,
                    document_type=doc.document_type,
                    department=doc.department,
                    version=doc.version,
                    section=section_title,
                    created_at=doc.created_at,
                    access_level=doc.access_level,
                )
            )
    return chunks


def chunk_documents(docs: list[RawDocument], **kwargs) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc, **kwargs))
    return all_chunks
