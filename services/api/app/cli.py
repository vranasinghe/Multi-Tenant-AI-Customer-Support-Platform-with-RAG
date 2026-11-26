"""Operational commands.

    python -m app.cli check-worker [--timeout SECONDS]
    python -m app.cli check-rls
    python -m app.cli init-storage
    python -m app.cli verify-data

`check-rls` exits 1 when any tenant table (has `org_id`, or is `organizations`) lacks enabled and
forced Row-Level Security plus at least one policy (docs/DATABASE.md §4.4).

`verify-data` prints a fingerprint of the database and its stored originals (no row contents), to
compare a restored backup with its source (docs/RECOVERY.md). It exits 1 when an original is
missing or a tenant table is unprotected.

Exits 0 when a Celery worker executed `system.ping` and returned its result via the backend.
"""

from __future__ import annotations

import argparse
import json
import uuid
from collections.abc import Callable

import structlog


def check_worker(timeout: float) -> int:
    from app.workers.tasks.system import ping  # needs configured settings  # noqa: PLC0415

    request_id = f"cli-{uuid.uuid4()}"
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        result = ping.apply_async()
        payload = result.get(timeout=timeout)
    except Exception as exc:  # report any broker/backend/timeout failure as a clean exit code
        print(json.dumps({"status": "error", "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    ok = isinstance(payload, dict) and payload.get("request_id") == request_id
    print(json.dumps({"status": "ok" if ok else "error", "task_id": result.id, "result": payload}))
    return 0 if ok else 1


def check_rls() -> int:
    from sqlalchemy import create_engine  # noqa: PLC0415

    from app.core.config import MigrationSettings  # noqa: PLC0415
    from app.core.rls import find_unprotected_tables  # noqa: PLC0415

    engine = create_engine(MigrationSettings().url)
    try:
        with engine.connect() as conn:
            missing = find_unprotected_tables(conn)
    finally:
        engine.dispose()
    print(json.dumps({"status": "error" if missing else "ok", "unprotected_tables": missing}))
    return 1 if missing else 0


def init_storage(timeout: float) -> int:
    """Create the private bucket (retrying while the storage service starts)."""
    import time  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415
    from app.rag.storage import StorageError, build_object_store  # noqa: PLC0415

    store = build_object_store(get_settings())
    deadline = time.monotonic() + timeout
    while True:
        try:
            store.ensure_ready()
        except StorageError as exc:
            if time.monotonic() > deadline:
                print(json.dumps({"status": "error", "detail": str(exc)}))
                return 1
            time.sleep(1.0)
        else:
            print(json.dumps({"status": "ok"}))
            return 0


def verify_data() -> int:
    from sqlalchemy import create_engine  # noqa: PLC0415

    from app.core.config import MigrationSettings, get_settings  # noqa: PLC0415
    from app.core.data_check import fingerprint  # noqa: PLC0415
    from app.rag.storage import build_object_store  # noqa: PLC0415

    engine = create_engine(MigrationSettings().url)
    try:
        with engine.connect() as conn:
            report = fingerprint(conn, build_object_store(get_settings()))
    finally:
        engine.dispose()
    print(json.dumps(report, indent=1, sort_keys=True, default=str))
    return 1 if report["objects"]["problems"] or report["unprotected_tables"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    worker = sub.add_parser("check-worker", help="round-trip a ping task through a worker")
    worker.add_argument("--timeout", type=float, default=15.0)
    sub.add_parser("check-rls", help="fail if a tenant table lacks forced RLS and a policy")
    storage = sub.add_parser("init-storage", help="create the private object-storage bucket")
    storage.add_argument("--timeout", type=float, default=60.0)
    sub.add_parser("verify-data", help="fingerprint data, protections and stored originals")
    args = parser.parse_args(argv)  # argparse exits with status 2 on unknown commands

    commands: dict[str, Callable[[], int]] = {
        "check-worker": lambda: check_worker(args.timeout),
        "check-rls": check_rls,
        "init-storage": lambda: init_storage(args.timeout),
        "verify-data": verify_data,
    }
    return commands[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
