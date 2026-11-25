from __future__ import annotations

import io
import zipfile

import pytest

from app.rag.errors import IngestionError
from app.rag.extract import Limits, extract_document, normalize_text
from app.rag.files import DOCX, PDF, TXT
from tests.support.documents import (
    DOCX_CONTENT_TYPES,
    make_blank_pdf,
    make_docx,
    make_encrypted_pdf,
    make_pdf,
)

LIMITS = Limits()


def code_of(data: bytes, mime: str, limits: Limits = LIMITS) -> str:
    with pytest.raises(IngestionError) as info:
        extract_document(data, mime, limits)
    return info.value.code


# --------------------------------------------------------------------------------- PDF


def test_pdf_text_is_extracted_per_page_with_page_numbers() -> None:
    doc = extract_document(make_pdf(["Alpha shipping policy", "Beta returns policy"]), PDF, LIMITS)

    assert doc.page_count == 2
    assert [(b.page, b.text) for b in doc.blocks] == [
        (1, "Alpha shipping policy"),
        (2, "Beta returns policy"),
    ]


def test_scanned_pdf_has_no_text() -> None:
    assert code_of(make_blank_pdf(2), PDF) == "no_text"


def test_encrypted_pdf_is_reported() -> None:
    assert code_of(make_encrypted_pdf(), PDF) == "encrypted"


@pytest.mark.parametrize(
    "data",
    [b"%PDF-1.4\nthis is not really a pdf", make_pdf(["hello"])[:120], b"%PDF-" + b"\x00" * 50],
)
def test_corrupt_pdf_is_reported(data: bytes) -> None:
    assert code_of(data, PDF) in {"corrupt", "no_text"}


def test_pdf_page_limit() -> None:
    assert code_of(make_pdf(["x"] * 4), PDF, Limits(max_pages=3)) == "too_many_pages"


def test_pdf_text_limit() -> None:
    assert code_of(make_pdf(["word " * 100]), PDF, Limits(max_chars=100)) == "too_large"


# -------------------------------------------------------------------------------- DOCX


def test_docx_headings_paragraphs_and_tables() -> None:
    data = make_docx(
        [
            ("h1", "Returns"),
            ("p", "Items can be returned within 30 days."),
            ("h2", "International"),
            ("p", "Customs fees are not refunded."),
            ("tr", "Region|Window"),
            ("tr", "EU|14 days"),
        ]
    )

    doc = extract_document(data, DOCX, LIMITS)

    body = [b for b in doc.blocks if not b.is_heading]
    assert doc.title == "Returns"
    assert body[0].heading_path == ("Returns",)
    assert body[1].heading_path == ("Returns", "International")
    assert [b.text for b in body[2:]] == ["Region | Window", "EU | 14 days"]


def test_docx_without_text_is_empty() -> None:
    assert code_of(make_docx([("p", "   ")]), DOCX) == "no_text"


def test_docx_that_is_not_a_zip_is_corrupt() -> None:
    assert code_of(b"PK\x03\x04 definitely not a zip", DOCX) == "corrupt"


def test_docx_missing_main_part_is_corrupt() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", DOCX_CONTENT_TYPES)
    assert code_of(out.getvalue(), DOCX) == "corrupt"


def test_macro_enabled_documents_are_rejected() -> None:
    macro_types = DOCX_CONTENT_TYPES.replace("document.main+xml", "document.macroEnabled.main+xml")
    data = make_docx([("p", "hello")], content_types=macro_types)
    assert code_of(data, DOCX) == "unsupported_type"


def test_zip_bomb_is_rejected_without_expanding_it() -> None:
    bomb = make_docx(
        [("p", "hello")], extra={"word/media/padding.bin": b"\x00" * (60 * 1024 * 1024)}
    )
    assert len(bomb) < 200_000  # tiny on the wire, huge when expanded
    limits = Limits(max_uncompressed_bytes=10 * 1024 * 1024)
    assert code_of(bomb, DOCX, limits) in {"corrupt", "too_large"}


def test_xml_entity_expansion_is_blocked() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>&b;</w:t></w:r></w:p></w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", DOCX_CONTENT_TYPES)
        archive.writestr("word/document.xml", bomb)
    assert code_of(out.getvalue(), DOCX) == "corrupt"


def test_zip_path_traversal_entries_are_rejected() -> None:
    data = make_docx([("p", "hello")], extra={"../evil.txt": b"x"})
    assert code_of(data, DOCX) == "corrupt"


# ---------------------------------------------------------------------------------- TXT


def test_txt_utf8_with_markdown_headings() -> None:
    raw = b"# Shipping\n\nWe ship in 2 days.\n\n## Rates\n\nFlat rate $5."
    doc = extract_document(raw, TXT, LIMITS)

    body = [b for b in doc.blocks if not b.is_heading]
    assert doc.title == "Shipping"
    assert [(b.text, b.heading_path) for b in body] == [
        ("We ship in 2 days.", ("Shipping",)),
        ("Flat rate $5.", ("Shipping", "Rates")),
    ]


def test_txt_heading_directly_followed_by_text_is_still_a_heading() -> None:
    raw = b"# Guide\n## Shipping\nWe ship fast.\nReally fast.\n## Returns\nThirty days."
    doc = extract_document(raw, TXT, LIMITS)

    assert [(b.text, b.heading_path, b.is_heading) for b in doc.blocks] == [
        ("Guide", ("Guide",), True),
        ("Shipping", ("Guide", "Shipping"), True),
        ("We ship fast. Really fast.", ("Guide", "Shipping"), False),
        ("Returns", ("Guide", "Returns"), True),
        ("Thirty days.", ("Guide", "Returns"), False),
    ]
    assert "##" not in doc.text


def test_txt_encodings() -> None:
    assert extract_document("café ☕".encode("utf-8-sig"), TXT, LIMITS).text == "café ☕"
    assert extract_document("naïve".encode("utf-16"), TXT, LIMITS).text == "naïve"
    assert extract_document("caf\xe9".encode("cp1252"), TXT, LIMITS).text == "café"


@pytest.mark.parametrize("data", [b"", b"   \n\n  ", b"\x00\x01\x02binary"])
def test_empty_or_binary_txt_is_rejected(data: bytes) -> None:
    assert code_of(data, TXT) in {"corrupt", "no_text"}


def test_unknown_type_is_unsupported() -> None:
    assert code_of(b"x", "image/png") == "unsupported_type"


# --------------------------------------------------------------------------- normalization


def test_normalization_cleans_hostile_text() -> None:
    raw = "Hel​lo  world\x00\x07\r\n\r\n\r\n\r\ninter-\nnational\t\tend  "
    assert normalize_text(raw) == "Hello world\n\ninternational end"


def test_normalization_folds_ligatures() -> None:
    assert normalize_text("ofﬁce") == "office"


def test_normalization_is_idempotent() -> None:
    once = normalize_text("  A  b\n\n\n\nc  ")
    assert normalize_text(once) == once
