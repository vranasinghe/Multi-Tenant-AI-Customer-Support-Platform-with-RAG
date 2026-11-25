from __future__ import annotations

import pytest

from app.rag.errors import IngestionError
from app.rag.files import DOCX, PDF, TXT, sanitize_filename, validate_upload
from tests.support.documents import make_docx, make_pdf


def test_accepts_each_supported_type_by_content() -> None:
    assert validate_upload("a.pdf", "application/pdf", make_pdf(["x"])[:512]).mime_type == PDF
    assert validate_upload("a.docx", None, make_docx([("p", "x")])[:512]).mime_type == DOCX
    assert (
        validate_upload("notes.txt", "text/plain; charset=utf-8", b"hello world").mime_type == TXT
    )


def test_generic_browser_type_is_fine_when_content_matches() -> None:
    assert (
        validate_upload("a.pdf", "application/octet-stream", make_pdf(["x"])[:64]).mime_type == PDF
    )
    assert validate_upload("a.md.txt", "", b"# heading").extension == "txt"


@pytest.mark.parametrize(
    ("name", "declared", "head"),
    [
        ("evil.exe", "application/octet-stream", b"MZ\x90\x00"),
        ("evil.pdf", "application/pdf", b"MZ\x90\x00\x03"),  # executable renamed .pdf
        ("fake.docx", None, b"%PDF-1.4"),  # PDF renamed .docx
        ("fake.txt", "text/plain", b"%PDF-1.4 hello"),  # PDF renamed .txt
        ("zip.txt", None, b"PK\x03\x04rest"),
        ("elf.txt", None, b"\x7fELF\x02\x01"),
        ("nul.txt", None, b"abc\x00def"),
        ("noext", None, b"hello"),
        ("script.js", "text/javascript", b"alert(1)"),
        ("a.pdf", "text/html", make_pdf(["x"])[:64]),  # declared type contradicts extension
        ("a.docx", "application/pdf", b"PK\x03\x04"),
        ("a.txt", "application/zip", b"hello"),
    ],
)
def test_rejects_mismatched_or_unsupported_files(
    name: str, declared: str | None, head: bytes
) -> None:
    with pytest.raises(IngestionError) as info:
        validate_upload(name, declared, head)
    assert info.value.code == "unsupported_type"


def test_utf16_text_is_allowed_only_with_a_bom() -> None:
    assert validate_upload("a.txt", None, b"\xff\xfeh\x00i\x00").extension == "txt"
    with pytest.raises(IngestionError):
        validate_upload("a.txt", None, b"h\x00i\x00")


def test_password_protected_ooxml_is_reported_as_encrypted() -> None:
    with pytest.raises(IngestionError) as info:
        validate_upload("a.docx", None, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert info.value.code == "encrypted"


def test_pdf_header_may_follow_a_short_preamble() -> None:
    assert validate_upload("a.pdf", None, b"\n\n  %PDF-1.7 ...").mime_type == PDF


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\report.pdf", "report.pdf"),
        ("a\u202etxt.exe.pdf", "atxt.exe.pdf"),  # bidi override stripped
        ("  spaced   name .pdf ", "spaced name .pdf"),
        ("nul\x00byte.txt", "nulbyte.txt"),
        (None, ""),
    ],
)
def test_filenames_are_sanitized_for_display(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_long_filenames_are_truncated() -> None:
    assert len(sanitize_filename("a" * 500 + ".pdf")) == 200
