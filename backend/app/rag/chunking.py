from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeSource:
    document_id: str
    document_type: str
    title: str
    content: str
    service_id: str | None = None
    environment: str | None = None
    version: str | None = None
    source: str = "postgresql"
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    content: str
    section: str


def clean_document(content: str) -> str:
    if not isinstance(content, str):
        raise ValueError("document content must be text")
    content = re.sub(r"(?i)(password|api[_ -]?key|jwt[_ -]?secret|authorization)\s*[:=]\s*[^\s]+", r"\1: [REDACTED]", content)
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = content.strip()
    if not content:
        raise ValueError("document content is empty")
    return content


def chunk_document(source: KnowledgeSource, *, chunk_size: int, overlap: int) -> list[KnowledgeChunk]:
    if overlap >= chunk_size:
        raise ValueError("chunk overlap must be smaller than chunk size")
    cleaned = clean_document(source.content)
    sections = re.split(r"(?m)(?=^#{1,6}\s+)", cleaned)
    chunks: list[KnowledgeChunk] = []
    for raw_section in sections:
        raw_section = raw_section.strip()
        if not raw_section:
            continue
        first_line, _, body = raw_section.partition("\n")
        section = first_line.lstrip("# ").strip() if first_line.startswith("#") else source.title
        text = raw_section
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            piece = text[start:end].strip()
            if piece:
                ordinal = len(chunks)
                digest = hashlib.sha256(f"{source.document_id}:{source.version or ''}:{ordinal}:{piece}".encode()).hexdigest()[:24]
                chunks.append(KnowledgeChunk(digest, piece, section))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
