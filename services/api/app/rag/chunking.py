"""Structure-aware chunking with overlap.

* Chunks never cross a heading boundary, so ``heading_path`` and page numbers stay truthful for
  citations.
* Paragraphs are packed greedily up to ``size_tokens``; oversized paragraphs are split on sentence
  boundaries, then on words as a last resort.
* Each chunk after the first in a section begins with up to ``overlap_tokens`` of the previous
  chunk's tail so an answer straddling a boundary is still retrievable.
* Token counts are estimates (~4 characters per token): good enough for sizing, and it avoids a
  tokenizer dependency. Sizes are therefore approximate, never exact.

Chunk text is stored as extracted. It is untrusted content and is only ever treated as data
(see ``app.rag.retrieval.render_context``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.rag.extract import Block

CHARS_PER_TOKEN = 4
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN)) if text else 0


@dataclass(frozen=True)
class ChunkingConfig:
    size_tokens: int = 350
    overlap_tokens: int = 50

    def __post_init__(self) -> None:
        if self.size_tokens < 16:
            msg = "size_tokens must be at least 16"
            raise ValueError(msg)
        if not 0 <= self.overlap_tokens < self.size_tokens:
            msg = "overlap_tokens must be >= 0 and smaller than size_tokens"
            raise ValueError(msg)


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    content: str
    embedded_text: str | None
    token_count: int
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int | None


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split text longer than ``max_chars`` on sentences, then on words."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            words = sentence.split(" ")
            line = ""
            for word in words:
                if line and len(line) + 1 + len(word) > max_chars:
                    pieces.append(line)
                    line = word
                else:
                    line = f"{line} {word}".strip()
                # a single "word" longer than the budget (e.g. a long URL/base64): hard cut
                while len(line) > max_chars:
                    pieces.append(line[:max_chars])
                    line = line[max_chars:]
            current = line
        elif current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(content: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(content) <= overlap_chars:
        return "" if overlap_chars <= 0 else content
    tail = content[-overlap_chars:]
    cut = tail.find(" ")
    return tail[cut + 1 :] if 0 <= cut < len(tail) - 1 else tail


def _context_header(title: str | None, path: tuple[str, ...]) -> str:
    parts = [p for p in (title, " > ".join(path) if path else None) if p]
    return "\n".join(parts)


def chunk_blocks(
    blocks: list[Block], config: ChunkingConfig, *, title: str | None = None
) -> list[Chunk]:
    max_chars = config.size_tokens * CHARS_PER_TOKEN
    overlap_chars = config.overlap_tokens * CHARS_PER_TOKEN

    # Group consecutive content blocks by heading path (headings only set the path).
    sections: list[tuple[tuple[str, ...], list[_Unit]]] = []
    for block in blocks:
        if block.is_heading:
            continue
        units = [_Unit(piece, block.page) for piece in _split_long(block.text, max_chars)]
        if sections and sections[-1][0] == block.heading_path:
            sections[-1][1].extend(units)
        else:
            sections.append((block.heading_path, units))

    chunks: list[Chunk] = []

    def emit(path: tuple[str, ...], pieces: list[_Unit], lead: str) -> str:
        body = "\n\n".join(u.text for u in pieces)
        content = f"{lead} {body}".strip() if lead else body
        pages = [u.page for u in pieces if u.page is not None]
        header = _context_header(title, path)
        embedded = f"{header}\n{content}" if header else None
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                content=content,
                embedded_text=embedded,
                token_count=estimate_tokens(content),
                heading_path=path,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
            )
        )
        return content

    for path, units in sections:
        current: list[_Unit] = []
        size = 0
        lead = ""
        for unit in units:
            extra = (
                len(unit.text)
                + (2 if current else 0)
                + (len(lead) + 1 if lead and not current else 0)
            )
            if current and size + extra > max_chars:
                content = emit(path, current, lead)
                lead = _overlap_tail(content, overlap_chars)
                current, size = [], 0
                extra = len(unit.text) + (len(lead) + 1 if lead else 0)
            current.append(unit)
            size += extra
        if current:
            emit(path, current, lead)
    return chunks
