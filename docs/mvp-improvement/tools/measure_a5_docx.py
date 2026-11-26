"""Where does a markup-heavy DOCX stop fitting in the 512 MiB parser address space?

Run inside the worker container after copying measure_a5.py to /tmp/measure_a5.py.
"""

import json
import sys
import types

source = open("/tmp/measure_a5.py", encoding="utf-8").read()  # noqa: SIM115, PTH123
base = types.ModuleType("measure_base")
exec(source[: source.index("cases: list")], base.__dict__)  # noqa: S102 - builders only

from app.rag.errors import IngestionError  # noqa: E402
from app.rag.extract import Limits  # noqa: E402
from app.rag.parser_runner import ParserLimits, ParserRunner  # noqa: E402

runner = ParserRunner(ParserLimits(), command=("-m", "tests.support.measure_parser"))
# Short runs of 40 characters; the character count scales the XML size.
for characters in (4_000_000, 6_000_000, 7_000_000, 8_000_000, 9_000_000):
    data, xml = base.rich_docx(characters, 40)
    row: dict[str, object] = {"xml_mib": round(xml / base.MIB, 1), "characters": characters}
    # The character limit is lifted here only so that XML size is the variable.
    try:
        parsed = runner.document(data, base.DOCX, Limits(max_chars=20_000_000))
        row |= json.loads(parsed.title or "{}") | {"result": "parsed"}
    except IngestionError as exc:
        row |= {"result": exc.code, "detail": exc.detail}
    sys.stdout.write("MEASURE " + json.dumps(row) + "\n")
