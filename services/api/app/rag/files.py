"""Upload validation: extension, declared MIME type and file signature must agree.

Browsers and clients routinely mislabel files, so the *content* decides. A file is accepted only
if (a) its extension is allowed, (b) the declared type is empty/generic or matches the extension,
and (c) its leading bytes match the format (or, for text, contain no binary content). That rejects
an executable renamed ``.pdf`` and a PDF renamed ``.txt``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.rag.errors import IngestionError

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT = "text/plain"

EXTENSIONS: dict[str, str] = {"pdf": PDF, "docx": DOCX, "txt": TXT}
_GENERIC_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
_ACCEPTED_DECLARED: dict[str, set[str]] = {
    PDF: {PDF, "application/x-pdf"},
    DOCX: {DOCX},
    TXT: {TXT, "text/markdown", "text/x-markdown"},
}

_BINARY_SIGNATURES = (
    b"MZ",  # Windows executables / DLLs
    b"\x7fELF",
    b"\xcf\xfa\xed\xfe",  # Mach-O
    b"\xca\xfe\xba\xbe",
    b"PK\x03\x04",  # zip (incl. docx/jar/apk)
    b"%PDF-",
    b"\xd0\xcf\x11\xe0",  # legacy OLE (doc, xls, encrypted OOXML)
    b"\x1f\x8b",  # gzip
    b"Rar!",
    b"7z\xbc\xaf",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF8",
)


@dataclass(frozen=True)
class ValidatedFile:
    filename: str  # sanitized display name
    extension: str
    mime_type: str  # canonical type derived from the content, not from the client


def sanitize_filename(raw: str | None) -> str:
    """Display name only (never used in storage keys): strip paths, controls and bidi tricks."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(
        ch
        for ch in name
        if unicodedata.category(ch) not in {"Cc", "Cf", "Cs", "Co", "Cn"}  # incl. RTL overrides
    )
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:200]


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        # UTF-16 text legitimately contains NULs; allow it only with a BOM.
        return head.startswith((b"\xff\xfe", b"\xfe\xff"))
    return not head.startswith(_BINARY_SIGNATURES)


def validate_upload(filename: str | None, declared_type: str | None, head: bytes) -> ValidatedFile:
    """Raise ``IngestionError("unsupported_type")`` unless the upload is a PDF, DOCX or TXT."""
    name = sanitize_filename(filename)
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    expected = EXTENSIONS.get(extension)
    if expected is None:
        raise IngestionError("unsupported_type", f"extension {extension!r}")

    declared = (declared_type or "").split(";", 1)[0].strip().lower()
    if declared not in _GENERIC_TYPES and declared not in _ACCEPTED_DECLARED[expected]:
        raise IngestionError("unsupported_type", f"declared type {declared!r} for .{extension}")

    if expected == DOCX and head.startswith(b"\xd0\xcf\x11\xe0"):
        # Password-protected OOXML files are OLE containers, not zip archives.
        raise IngestionError("encrypted", "OLE container (encrypted or legacy .doc)")
    if expected == PDF:
        ok = b"%PDF-" in head[:1024]
    elif expected == DOCX:
        ok = head.startswith(b"PK\x03\x04")
    else:
        ok = _looks_like_text(head[:4096])
    if not ok:
        raise IngestionError("unsupported_type", "content does not match the file extension")
    return ValidatedFile(filename=name, extension=extension, mime_type=expected)
