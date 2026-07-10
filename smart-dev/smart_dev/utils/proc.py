"""Safe subprocess execution helper (cross-platform, timed, non-shell)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Container
from pathlib import Path
from typing import Any


def which(name: str) -> str | None:
    return shutil.which(name)


def git_changed_files(
    root: str | Path, base: str, exts: Container[str] | None = None
) -> tuple[list[str], str | None]:
    """Files changed vs ``base`` (working-tree changes + untracked), as relative
    POSIX paths. Filtered to ``exts`` (by suffix) when given.

    Returns ``(files, error)``. On any git failure ``error`` is a message and
    ``files`` is empty; callers should surface it rather than silently scan all.
    """
    root = Path(root)
    diff = run_command(["git", "diff", "--name-only", base], cwd=root, timeout=30)
    if diff["exit_code"] is None:
        return [], (diff["stderr"] or "git unavailable").strip()[:200]
    if diff["exit_code"] != 0 and not diff["stdout"]:
        return [], (diff["stderr"] or "not a git repository or unknown ref").strip()[:200]

    names = set(diff["stdout"].splitlines())
    untracked = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root, timeout=30
    )
    names.update(untracked["stdout"].splitlines())

    out: list[str] = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        p = root / name
        if p.is_file() and (exts is None or p.suffix in exts):
            out.append(name)
    return out, None


def run_command(
    cmd: list[str], cwd: str | Path, timeout: int = 300
) -> dict[str, Any]:
    """Run ``cmd`` in ``cwd`` without a shell. Never raises — returns a dict."""
    exe = which(cmd[0]) or cmd[0]
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except FileNotFoundError:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": f"command not found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": f"timed out after {timeout}s"}
