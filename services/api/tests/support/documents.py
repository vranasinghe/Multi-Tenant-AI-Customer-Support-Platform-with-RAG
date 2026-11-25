"""Builders for test documents: real PDF/DOCX bytes generated in-process (no fixtures on disk)."""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape


def make_pdf(pages: list[str]) -> bytes:
    """A minimal, valid text PDF with one line of text per page (Helvetica)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog_id = add(b"")  # patched below
    pages_id = add(b"")
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for text in pages:
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1", "replace")
        content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(
            add(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
            )
        )
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def make_blank_pdf(pages: int = 1) -> bytes:
    """A PDF with no extractable text (what a scan looks like to a text extractor)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(612, 792)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_encrypted_pdf(text: str = "secret", password: str = "hunter2") -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf([text]))))
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)


def make_docx(
    items: list[tuple[str, str]],
    *,
    content_types: str = DOCX_CONTENT_TYPES,
    extra: dict[str, bytes] | None = None,
) -> bytes:
    """``items``: ("h1"|"h2"|"p"|"tr", text). ``tr`` rows use ``a|b|c`` for cells."""
    body: list[str] = []
    for kind, text in items:
        if kind in {"h1", "h2", "h3"}:
            style = f'<w:pPr><w:pStyle w:val="Heading{kind[1]}"/></w:pPr>'
            body.append(f"<w:p>{style}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>")
        elif kind == "tr":
            cells = "".join(
                f"<w:tc><w:p><w:r><w:t>{escape(c)}</w:t></w:r></w:p></w:tc>"
                for c in text.split("|")
            )
            body.append(f"<w:tbl><w:tr>{cells}</w:tr></w:tbl>")
        else:
            body.append(f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>")
    document = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{_W}"><w:body>'
        + "".join(body)
        + "</w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return out.getvalue()
