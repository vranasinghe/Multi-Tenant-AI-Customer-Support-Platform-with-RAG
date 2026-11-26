"""Fail a run whose tests did not really run.

    python check_junit.py report.xml [--allow-skip CLASSNAME_PREFIX]... [--min-tests N]

pytest exits 0 when tests skip, so a missing service or variable looks like success. Every skip
must be named here by the job that has another job running it.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--allow-skip", action="append", default=[])
    parser.add_argument("--min-tests", type=int, default=1)
    args = parser.parse_args()

    cases = list(ET.parse(args.report).getroot().iter("testcase"))  # noqa: S314 - our own report
    failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    skipped = [c for c in cases if c.find("skipped") is not None]
    allowed = tuple(args.allow_skip)
    unexpected = [c for c in skipped if not (allowed and c.get("classname", "").startswith(allowed))]
    ran = len(cases) - len(skipped)

    print(
        f"tests={len(cases)} ran={ran} failed={len(failed)} skipped={len(skipped)} "
        f"unexpected_skips={len(unexpected)}"
    )
    for case in unexpected[:40]:
        reason = case.find("skipped").get("message", "")  # type: ignore[union-attr]
        print(f"  unexpected skip: {case.get('classname')}::{case.get('name')} ({reason})")
    if ran < args.min_tests:
        print(f"  only {ran} tests ran; at least {args.min_tests} expected")
    return 1 if failed or unexpected or ran < args.min_tests else 0


if __name__ == "__main__":
    sys.exit(main())
