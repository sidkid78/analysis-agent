"""Cross-platform path resolution for tool arguments.

Tools receive user-supplied paths (often absolute, sometimes with ``~`` or
relative). These helpers normalize them and fail with clear messages rather than
raising deep in the analysis code.
"""

from __future__ import annotations

from pathlib import Path


class PathError(Exception):
    """Raised for invalid or missing paths, with a user-facing message."""


def _resolve(path: str | Path) -> Path:
    p = Path(path).expanduser()
    try:
        return p.resolve()
    except (OSError, RuntimeError) as exc:  # e.g. symlink loops
        raise PathError(f"Could not resolve path '{path}': {exc}") from exc


def resolve_dir(path: str | Path) -> Path:
    """Resolve to an existing directory or raise :class:`PathError`."""
    p = _resolve(path)
    if not p.exists():
        raise PathError(f"Directory not found: {p}")
    if not p.is_dir():
        raise PathError(f"Not a directory: {p}")
    return p


def resolve_file(path: str | Path) -> Path:
    """Resolve to an existing file or raise :class:`PathError`."""
    p = _resolve(path)
    if not p.exists():
        raise PathError(f"File not found: {p}")
    if not p.is_file():
        raise PathError(f"Not a file: {p}")
    return p
