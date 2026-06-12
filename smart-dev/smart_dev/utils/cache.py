"""Lightweight per-file analysis cache keyed by path + modification time.

Avoids re-analyzing unchanged files across repeated tool calls within a process.
Purely an optimization — a cache miss just recomputes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class FileCache:
    def __init__(self) -> None:
        # path -> (mtime_ns, value)
        self._store: dict[str, tuple[int, Any]] = {}

    def get_or_compute(self, path: Path, compute: Callable[[Path], Any]) -> Any:
        key = str(path)
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return compute(path)
        hit = self._store.get(key)
        if hit is not None and hit[0] == mtime:
            return hit[1]
        value = compute(path)
        self._store[key] = (mtime, value)
        return value

    def clear(self) -> None:
        self._store.clear()
