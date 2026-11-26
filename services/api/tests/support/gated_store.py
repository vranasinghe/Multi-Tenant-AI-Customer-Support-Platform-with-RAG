"""An object store whose writes and reads can be paused or broken at one precise moment."""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.rag.storage import ObjectNotFoundError, ObjectStore

Hook = Callable[[str, bytes], None]


def _nothing(_key: str, _data: bytes) -> None:
    return None


class GatedStore:
    """Delegates to a real store. ``before_put``/``after_put``/``before_get`` run around calls."""

    def __init__(self, inner: ObjectStore) -> None:
        self.inner = inner
        self.written: list[str] = []
        self.before_put: Hook = _nothing
        self.after_put: Hook = _nothing
        self.before_get: Callable[[str], None] = lambda _key: None

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self.before_put(key, data)
        self.inner.put(key, data, content_type=content_type)
        self.written.append(key)
        self.after_put(key, data)

    def get(self, key: str, *, max_bytes: int) -> bytes:
        self.before_get(key)
        return self.inner.get(key, max_bytes=max_bytes)

    def delete(self, key: str) -> None:
        self.inner.delete(key)

    def ensure_ready(self) -> None:
        self.inner.ensure_ready()

    def read(self, key: str) -> str | None:
        """The stored text, or ``None`` if there is no such object."""
        try:
            return self.inner.get(key, max_bytes=10_000_000).decode()
        except ObjectNotFoundError:
            return None

    def surviving(self) -> list[str]:
        """Every key ever written through this store that still holds an object."""
        return sorted(key for key in set(self.written) if self.read(key) is not None)


class Pause:
    """Blocks the first caller whose data contains ``marker`` until ``release`` is set."""

    def __init__(self, marker: str, then: Callable[[], None] | None = None) -> None:
        self.marker = marker.encode()
        self.reached = threading.Event()
        self.release = threading.Event()
        self.then = then

    def __call__(self, _key: str, data: bytes) -> None:
        if self.marker not in data or self.reached.is_set():
            return
        self.reached.set()
        assert self.release.wait(30), "the paused writer was never released"
        if self.then is not None:
            self.then()
