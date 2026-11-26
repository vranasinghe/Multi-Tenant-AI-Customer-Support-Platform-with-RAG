"""Do the default parser budgets (60 s wall, 30 s CPU, 512 MiB) fit supported documents?

Builds the largest ordinary documents the approved limits accept (25 MiB upload, 500 PDF pages,
5 million extracted characters, 5 MiB fetched page) and parses each in the real, limited child.
Nothing here is hostile. Run inside the worker container:

    docker compose ... exec -T worker python - < docs/mvp-improvement/tools/measure_a5.py
"""

import io
import json
import sys
import time
import zipfile

from app.rag.errors import IngestionError
from app.rag.extract import Limits
from app.rag.files import DOCX, PDF, TXT
from app.rag.parser_runner import ParserLimits, ParserRunner
from tests.support.documents import DOCX_CONTENT_TYPES, make_pdf

MIB = 1024 * 1024
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
LINE = "Standard shipping to the United States takes three to five business days after dispatch. "


def rich_docx(characters: int, run_length: int) -> tuple[bytes, int]:
    """A Word file with styled runs, as editors produce them. Returns (zip, XML size)."""
    run_text = (LINE * (run_length // len(LINE) + 1))[:run_length]
    run = (
        '<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>'
        f'<w:lang w:val="en-US"/></w:rPr><w:t xml:space="preserve">{run_text}</w:t></w:r>'
    )
    paragraph = (
        '<w:p><w:pPr><w:spacing w:after="120"/><w:jc w:val="both"/></w:pPr>' + run * 4 + "</w:p>"
    )
    count = characters // (run_length * 4)
    xml = (
        f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>'
        + paragraph * count
        + "</w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr("[Content_Types].xml", DOCX_CONTENT_TYPES)
        archive.writestr("word/document.xml", xml)
    return out.getvalue(), len(xml)


def text_of(unit: str, characters: int) -> bytes:
    paragraph = (unit * (400 // len(unit) + 1))[:400] + "\n\n"
    return (paragraph * (characters // len(paragraph))).encode()


def html_page(size: int) -> bytes:
    block = f"<div><p>{LINE}<a href='/p/1'>link</a></p></div>\n"
    return ("<html><body><main>" + block * (size // len(block)) + "</main></body></html>").encode()


cases: list[tuple[str, str | None, bytes, dict[str, int]]] = []
cases.append(("pdf 500 pages, 1.5M chars", PDF, make_pdf([LINE * 34] * 500), {}))
for label, run_length in (("typical runs", 400), ("short runs", 40)):
    data, xml = rich_docx(4_900_000, run_length)
    cases.append((f"docx 4.9M chars, {label}, XML {xml // MIB} MiB", DOCX, data, {}))
cases.append(("txt 4.9M ascii chars", TXT, text_of(LINE, 4_900_000), {}))
cases.append(("txt 4.9M cjk chars", TXT, text_of("运输需要三到五天。", 4_900_000), {}))
cases.append(("txt 4.9M emoji chars", TXT, text_of("\U0001f4e6 shipping ", 4_900_000), {}))
cases.append(("txt over the character limit, 24 MiB", TXT, text_of(LINE, 24 * MIB), {}))
cases.append(("html 5 MiB (fetch limit)", None, html_page(5 * MIB - 1024), {}))

runner = ParserRunner(ParserLimits(), command=("-m", "tests.support.measure_parser"))
results = []
for name, mime, data, _ in cases:
    started = time.monotonic()
    row: dict[str, object] = {"case": name, "input_mib": round(len(data) / MIB, 2)}
    try:
        if mime is None:
            parsed = runner.html(data, "https://example.com/")
        else:
            parsed = runner.document(data, mime, Limits())
        row |= json.loads(parsed.title or "{}")
        row |= {"result": "parsed", "blocks": len(parsed.blocks)}
    except IngestionError as exc:
        row |= {"result": exc.code, "detail": exc.detail}
    row["wall_seconds"] = round(time.monotonic() - started, 2)
    results.append(row)
    sys.stdout.write("MEASURE " + json.dumps(row) + "\n")
    sys.stdout.flush()
