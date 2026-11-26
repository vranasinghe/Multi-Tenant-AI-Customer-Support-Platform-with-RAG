"""AUD-05 baseline reproduction. Small synthetic inputs only; every probe is bounded on its own.

Run before the change:  docker compose ... exec -T api python - < docs/mvp-improvement/tools/repro_a5.py
Nothing here can exhaust the host: the largest decompressed buffer is 20 MB, the deepest HTML
nesting is 8,000 elements and the slow "parser" sleeps for two seconds.
"""

import inspect
import io
import json
import os
import resource
import time
import zlib

from app.rag import crawler, pipeline
from app.rag.extract import Limits, extract_document
from app.rag.html_extract import extract_html
from app.workers.celery_app import celery_app
from app.workers.tasks import ingest

out: dict[str, object] = {}

# 1. Where parsing happens: direct calls from the long-lived worker modules.
out["extract_stored_calls_parser_in_process"] = [
    line.strip()
    for line in inspect.getsource(pipeline.extract_stored).splitlines()
    if "extract_" in line and "def " not in line
]
out["crawler_calls_parser_in_process"] = [
    line.strip() for line in inspect.getsource(crawler.crawl).splitlines() if "extract_html(" in line
]

# 2. No execution deadline on any ingestion task.
celery_app.loader.import_default_modules()
out["celery_global_limits"] = {
    "task_soft_time_limit": celery_app.conf.task_soft_time_limit,
    "task_time_limit": celery_app.conf.task_time_limit,
    "task_annotations": str(celery_app.conf.task_annotations),
}
out["task_limits"] = {
    t.name: {"soft": t.soft_time_limit, "hard": t.time_limit}
    for t in (ingest.process_document, ingest.crawl_source)
}

# 3. A slow parser is not interrupted by anything.
original = pipeline.extract_document


def slow(data, mime, limits):
    time.sleep(2)
    return original(data, mime, limits)


pipeline.extract_document = slow


class _Rt:
    limits = Limits()


started = time.monotonic()
pipeline.extract_stored(_Rt(), b"bounded slow parser fixture", "text/plain", "x.txt")
out["slow_parser_ran_to_completion_seconds"] = round(time.monotonic() - started, 2)
out["slow_parser_pid_is_caller_pid"] = os.getpid()
pipeline.extract_document = original

# 4. HTML parser time grows super-linearly with nesting depth (bounded to 8,000 elements).
timings = {}
for depth in (2000, 4000, 8000):
    markup = "<div>x" * depth
    started = time.monotonic()
    extract_html(markup, "https://example.com/")
    timings[str(depth)] = {"bytes": len(markup), "seconds": round(time.monotonic() - started, 3)}
out["html_nesting_timings"] = timings


# 5. A small PDF expands in the caller's memory before the text limit is consulted.
def compressed_pdf(size: int) -> bytes:
    text = b"BT /F1 12 Tf 72 720 Td (" + b"a" * 64 + b") Tj ET\n"
    stream = text + b" " * (size - len(text))
    packed = zlib.compress(stream, 9)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
        b"/Resources << /Font << /F1 3 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(packed) + packed + b"\nendstream",
    ]
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n")
    for offset in offsets:
        buffer.write(f"{offset:010d} 00000 n \n".encode())
    buffer.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return buffer.getvalue()


data = compressed_pdf(20 * 1024 * 1024)
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
started = time.monotonic()
try:
    extract_document(data, "application/pdf", Limits())
    result = "extracted"
except Exception as exc:  # the probe records whatever happens
    result = type(exc).__name__ + ":" + str(exc)[:80]
out["compressed_pdf"] = {
    "input_bytes": len(data),
    "decompressed_stream_bytes": 20 * 1024 * 1024,
    "result": result,
    "seconds": round(time.monotonic() - started, 3),
    "caller_peak_rss_growth_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before,
}
out["rlimit_as"] = resource.getrlimit(resource.RLIMIT_AS)
out["rlimit_cpu"] = resource.getrlimit(resource.RLIMIT_CPU)
print(json.dumps(out, indent=2, default=str))
