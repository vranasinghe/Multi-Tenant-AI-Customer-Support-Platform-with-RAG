"""Text extraction and normalization for PDF, DOCX and TXT.

Inputs are hostile until proven otherwise: every extractor enforces page, size and
decompression limits, never executes anything embedded in the file, and maps every failure to a
stable ``IngestionError`` code (``corrupt``, ``encrypted``, ``no_text``...). Extracted text is
returned as *data* (``Block`` objects); nothing here interprets it as instructions.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.rag.errors import IngestionError
from app.rag.files import DOCX, PDF, TXT

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

_ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD])
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")
_BLANKS = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_MAIN_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


@dataclass(frozen=True)
class Limits:
    max_pages: int = 500
    max_chars: int = 5_000_000
    max_uncompressed_bytes: int = 100 * 1024 * 1024
    max_zip_entries: int = 2000
    max_zip_ratio: int = 200


@dataclass(frozen=True)
class Block:
    """A paragraph, table or heading with where it came from."""

    text: str
    page: int | None = None
    heading_path: tuple[str, ...] = ()
    is_heading: bool = False


@dataclass
class ExtractedDocument:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None
    title: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)


def normalize_text(text: str) -> str:
    """Canonical text: NFKC, no control/zero-width characters, tidy whitespace and line breaks."""
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "inter-\nnational" -> "international"
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANKS.sub("\n\n", text).strip()


def _paragraphs(text: str) -> list[str]:
    """Split on blank lines; single line breaks inside a paragraph become spaces."""
    parts = [re.sub(r"\s*\n\s*", " ", part).strip() for part in re.split(r"\n\s*\n", text)]
    return [part for part in parts if part]


# ------------------------------------------------------------------------------------- PDF


def _extract_pdf(data: bytes, limits: Limits) -> ExtractedDocument:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")  # many PDFs are "encrypted" with an empty password
            except Exception as exc:
                raise IngestionError("encrypted") from exc
            if not decrypted:
                raise IngestionError("encrypted")
        page_total = len(reader.pages)
        if page_total > limits.max_pages:
            raise IngestionError("too_many_pages", f"{page_total} pages")
        doc = ExtractedDocument(page_count=page_total)
        chars = 0
        for number, page in enumerate(reader.pages, start=1):
            text = normalize_text(page.extract_text() or "")
            chars += len(text)
            if chars > limits.max_chars:
                raise IngestionError("too_large", "extracted text exceeds the limit")
            doc.blocks.extend(Block(text=p, page=number) for p in _paragraphs(text))
        metadata = reader.metadata
        title = normalize_text(str(metadata.title)) if metadata and metadata.title else ""
        doc.title = title[:300] or None
    except IngestionError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise IngestionError("corrupt", type(exc).__name__) from exc
    return doc


# ------------------------------------------------------------------------------------ DOCX


def _check_zip(archive: zipfile.ZipFile, limits: Limits) -> None:
    infos = archive.infolist()
    if len(infos) > limits.max_zip_entries:
        raise IngestionError("corrupt", "too many archive entries")
    total = 0
    for info in infos:
        total += info.file_size
        if (
            info.file_size > 1024 * 1024
            and info.file_size > info.compress_size * limits.max_zip_ratio
        ):
            raise IngestionError("corrupt", "suspicious compression ratio")
        if info.filename.startswith(("/", "..")) or ".." in info.filename.split("/"):
            raise IngestionError("corrupt", "unsafe archive path")
    if total > limits.max_uncompressed_bytes:
        raise IngestionError("too_large", "archive expands beyond the limit")


def _read_member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    with archive.open(name) as handle:
        data = handle.read(limit + 1)  # never trust the header's size; cap the actual read
    if len(data) > limit:
        raise IngestionError("too_large", "archive member expands beyond the limit")
    return data


def _run_text(paragraph: Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{W}t" and node.text:
            parts.append(node.text)
        elif node.tag in {f"{W}tab"}:
            parts.append("\t")
        elif node.tag in {f"{W}br", f"{W}cr"}:
            parts.append("\n")
    return "".join(parts)


def _heading_level(paragraph: Element) -> int | None:
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    value = (style.get(f"{W}val") if style is not None else None) or ""
    if value.lower() == "title":
        return 1
    match = re.fullmatch(r"(?i)heading\s*([1-6])", value)
    return int(match.group(1)) if match else None


def _extract_docx(data: bytes, limits: Limits) -> ExtractedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _check_zip(archive, limits)
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise IngestionError("corrupt", "not a Word document")
            types = _read_member(archive, "[Content_Types].xml", 1024 * 1024)
            if DOCX_MAIN_TYPE.encode() not in types:
                raise IngestionError("unsupported_type", "not a plain .docx (macro or template)")
            root = SafeET.fromstring(
                _read_member(archive, "word/document.xml", limits.max_uncompressed_bytes)
            )
    except IngestionError:
        raise
    except (
        zipfile.BadZipFile,
        DefusedXmlException,
        SafeET.ParseError,
        RuntimeError,
        OSError,
    ) as exc:
        raise IngestionError("corrupt", type(exc).__name__) from exc

    body = root.find(f"{W}body")
    if body is None:
        raise IngestionError("corrupt", "missing body")
    doc = ExtractedDocument()
    headings: list[tuple[int, str]] = []
    chars = 0

    def add(text: str, *, heading: bool = False) -> None:
        nonlocal chars
        cleaned = normalize_text(text)
        if not cleaned:
            return
        chars += len(cleaned)
        if chars > limits.max_chars:
            raise IngestionError("too_large", "extracted text exceeds the limit")
        path = tuple(h for _, h in headings)
        doc.blocks.append(Block(text=cleaned, heading_path=path, is_heading=heading))

    for element in body:
        if element.tag == f"{W}p":
            text = _run_text(element)
            level = _heading_level(element)
            if level is not None and text.strip():
                headings[:] = [(lvl, h) for lvl, h in headings if lvl < level]
                headings.append((level, normalize_text(text)[:200]))
                if doc.title is None:
                    doc.title = headings[-1][1]
                add(text, heading=True)
            else:
                add(text)
        elif element.tag == f"{W}tbl":
            for row in element.iter(f"{W}tr"):
                cells = [normalize_text(_run_text(cell)) for cell in row.findall(f"{W}tc")]
                add(" | ".join(c for c in cells if c))
    return doc


# ------------------------------------------------------------------------------------- TXT


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="strict")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if b"\x00" in data[:8192]:
        raise IngestionError("corrupt", "binary content")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1252")
    except UnicodeDecodeError as exc:
        raise IngestionError("corrupt", "undecodable text") from exc
    return text


def _extract_txt(data: bytes, limits: Limits) -> ExtractedDocument:
    try:
        raw = decode_text(data)
    except UnicodeError as exc:
        raise IngestionError("corrupt", "undecodable text") from exc
    text = normalize_text(raw)
    if len(text) > limits.max_chars:
        raise IngestionError("too_large", "text exceeds the limit")
    doc = ExtractedDocument()
    headings: list[tuple[int, str]] = []
    lines: list[str] = []

    def flush() -> None:
        body = " ".join(line.strip() for line in lines if line.strip())
        lines.clear()
        if body:
            doc.blocks.append(Block(text=body, heading_path=tuple(h for _, h in headings)))

    # Line-based: a Markdown heading is a heading even when the paragraph follows it directly.
    for line in text.split("\n"):
        match = _MD_HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            headings[:] = [(lvl, h) for lvl, h in headings if lvl < level]
            headings.append((level, match.group(2)))
            if doc.title is None:
                doc.title = match.group(2)[:300]
            path = tuple(h for _, h in headings)
            doc.blocks.append(Block(text=match.group(2), heading_path=path, is_heading=True))
        elif not line.strip():
            flush()
        else:
            lines.append(line)
    flush()
    return doc


# ------------------------------------------------------------------------------- dispatch


def extract_document(data: bytes, mime_type: str, limits: Limits) -> ExtractedDocument:
    """Extract and validate. Raises ``IngestionError`` (never returns an empty document)."""
    if not data:
        raise IngestionError("corrupt", "empty file")
    if mime_type == PDF:
        doc = _extract_pdf(data, limits)
    elif mime_type == DOCX:
        doc = _extract_docx(data, limits)
    elif mime_type == TXT:
        doc = _extract_txt(data, limits)
    else:
        raise IngestionError("unsupported_type", mime_type)
    if not any(not block.is_heading for block in doc.blocks) or not doc.text.strip():
        raise IngestionError("no_text")
    return doc
