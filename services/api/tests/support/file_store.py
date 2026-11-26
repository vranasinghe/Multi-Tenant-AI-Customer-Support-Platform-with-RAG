"""An object store on disk, shared between a test process and a real worker subprocess."""

from __future__ import annotations

from pathlib import Path

from app.rag.storage import ObjectNotFoundError, StorageError


class FileObjectStore:
    def __init__(self, directory: str | Path) -> None:
        self._root = Path(directory)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._root / key.replace("/", "__")

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self._path(key).write_bytes(data)

    def get(self, key: str, *, max_bytes: int) -> bytes:
        try:
            data = self._path(key).read_bytes()
        except FileNotFoundError as exc:
            msg = "object not found"
            raise ObjectNotFoundError(msg) from exc
        if len(data) > max_bytes:
            msg = "object is larger than allowed"
            raise StorageError(msg)
        return data

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def ensure_ready(self) -> None:
        return None
