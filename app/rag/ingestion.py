"""Document ingestion: load raw files (md/txt/html/pdf), extract metadata,
and clean text before chunking.

Supported formats:
- Markdown (.md): YAML frontmatter (--- ... ---) parsed for
  document_type/department/version/access_level; body is the content.
- Plain text (.txt): no frontmatter; metadata defaults are used.
- HTML (.html): parsed with BeautifulSoup, tags stripped to text.
- PDF (.pdf): text extracted page-by-page with pypdf.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_ACCESS_LEVEL = "standard"


@dataclass
class RawDocument:
    document_id: str
    document_name: str
    document_type: str
    department: str | None
    version: str
    access_level: str
    file_path: str
    created_at: datetime
    text: str
    metadata: dict = field(default_factory=dict)


def _parse_frontmatter(raw_text: str) -> tuple[dict, str]:
    """Parse a leading '---\\n...\\n---' YAML-ish block without requiring a
    YAML dependency (frontmatter here is always flat key: value pairs)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_text, re.DOTALL)
    if not match:
        return {}, raw_text
    fm_block, body = match.groups()
    meta = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, body


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def load_markdown(path: Path) -> RawDocument:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    # Title = first H1, else filename
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("_", " ").title()

    return RawDocument(
        document_id=path.stem,
        document_name=title,
        document_type=meta.get("document_type", "guide"),
        department=meta.get("department"),
        version=meta.get("version", "1.0"),
        access_level=meta.get("access_level", DEFAULT_ACCESS_LEVEL),
        file_path=str(path),
        created_at=datetime.utcnow(),
        text=_clean_text(body),
        metadata=meta,
    )


def load_text(path: Path) -> RawDocument:
    raw = path.read_text(encoding="utf-8")
    return RawDocument(
        document_id=path.stem,
        document_name=path.stem.replace("_", " ").title(),
        document_type="guide",
        department=None,
        version="1.0",
        access_level=DEFAULT_ACCESS_LEVEL,
        file_path=str(path),
        created_at=datetime.utcnow(),
        text=_clean_text(raw),
    )


def load_html(path: Path) -> RawDocument:
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    title_tag = soup.find("title") or soup.find("h1")
    title = title_tag.get_text().strip() if title_tag else path.stem.replace("_", " ").title()
    text = soup.get_text(separator="\n")
    return RawDocument(
        document_id=path.stem,
        document_name=title,
        document_type="guide",
        department=None,
        version="1.0",
        access_level=DEFAULT_ACCESS_LEVEL,
        file_path=str(path),
        created_at=datetime.utcnow(),
        text=_clean_text(text),
    )


def load_pdf(path: Path) -> RawDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages_text)
    return RawDocument(
        document_id=path.stem,
        document_name=path.stem.replace("_", " ").title(),
        document_type="guide",
        department=None,
        version="1.0",
        access_level=DEFAULT_ACCESS_LEVEL,
        file_path=str(path),
        created_at=datetime.utcnow(),
        text=_clean_text(text),
    )


_LOADERS = {
    ".md": load_markdown,
    ".txt": load_text,
    ".html": load_html,
    ".htm": load_html,
    ".pdf": load_pdf,
}


def load_document(path: Path) -> RawDocument:
    suffix = path.suffix.lower()
    if suffix not in _LOADERS:
        raise ValueError(f"Unsupported document type: {suffix} ({path})")
    return _LOADERS[suffix](path)


def load_documents_from_dir(directory: Path) -> list[RawDocument]:
    docs = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in _LOADERS:
            docs.append(load_document(path))
    return docs
