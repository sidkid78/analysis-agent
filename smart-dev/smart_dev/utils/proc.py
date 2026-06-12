"""Safe subprocess execution helper (cross-platform, timed, non-shell)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def which(name: str) -> str | None:
    return shutil.which(name)


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
