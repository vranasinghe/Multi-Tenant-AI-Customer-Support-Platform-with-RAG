"""Corrected baseline memory probe: peak Python allocations while parsing a 21 KB PDF.

`ru_maxrss` in repro_a5.py reported no growth because the peak is inherited across exec in this
environment; tracemalloc measures the allocations made by the parser itself.
"""

import json
import sys
import tracemalloc
import types

source = open("/tmp/repro_a5.py", encoding="utf-8").read()  # noqa: SIM115, PTH123
module = types.ModuleType("repro_pdf")
# Reuse only the bounded fixture builder, not the probes around it.
start = source.index("def compressed_pdf")
end = source.index("data = compressed_pdf")
exec("import io\nimport zlib\n" + source[start:end], module.__dict__)  # noqa: S102

from app.rag.extract import Limits, extract_document  # noqa: E402

data = module.compressed_pdf(20 * 1024 * 1024)
tracemalloc.start()
extract_document(data, "application/pdf", Limits())
current, peak = tracemalloc.get_traced_memory()
sys.stdout.write(
    json.dumps({"input_bytes": len(data), "peak_traced_bytes_in_caller": peak}) + "\n"
)
