"""Detect the project's test framework, run it, and summarize results."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..utils import get_logger, resolve_dir, run_command, which

log = get_logger(__name__)

_PYTEST_SUMMARY = re.compile(
    r"(?:(\d+) failed)?[,\s]*(?:(\d+) passed)?[,\s]*(?:(\d+) skipped)?[,\s]*(?:(\d+) error)?",
)


def run_tests(path: str, timeout: int = 600) -> dict[str, Any]:
    """Detect and run the test suite for a project directory.

    Supports pytest (Python) and the npm/pnpm `test` script (Node).
    """
    root = resolve_dir(path)
    framework, command = _detect(root)
    if framework is None:
        return {"project": str(root), "framework": None,
                "message": "No recognized test setup (pytest or package.json 'test' script)."}

    log.info("run_tests: %s -> %s", root, command)
    result = run_command(command, cwd=root, timeout=timeout)
    output = (result["stdout"] + "\n" + result["stderr"]).strip()
    summary = _summarize(framework, output)
    return {
        "project": str(root),
        "framework": framework,
        "command": " ".join(command),
        "exit_code": result["exit_code"],
        "passed": result["ok"],
        **summary,
        "output_tail": "\n".join(output.splitlines()[-25:]),
    }


def _detect(root: Path) -> tuple[str | None, list[str]]:
    has_pytest = (
        (root / "pytest.ini").exists()
        or (root / "tests").is_dir()
        or any(root.glob("test_*.py"))
        or _pyproject_mentions(root, "pytest")
    )
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if isinstance(data.get("scripts"), dict) and "test" in data["scripts"]:
                pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
                return f"{pm} test", [pm, "test"]
        except (json.JSONDecodeError, OSError):
            pass
    if has_pytest:
        py = "python" if which("python") else "python3"
        return "pytest", [py, "-m", "pytest", "-q"]
    return None, []


def _pyproject_mentions(root: Path, needle: str) -> bool:
    pp = root / "pyproject.toml"
    try:
        return pp.exists() and needle in pp.read_text(encoding="utf-8")
    except OSError:
        return False


def _summarize(framework: str, output: str) -> dict[str, Any]:
    if "pytest" in framework:
        passed = _last_int(r"(\d+) passed", output)
        failed = _last_int(r"(\d+) failed", output)
        skipped = _last_int(r"(\d+) skipped", output)
        errors = _last_int(r"(\d+) error", output)
        cov = _last_int(r"TOTAL.+?(\d+)%", output)
        return {"tests_passed": passed, "tests_failed": failed,
                "tests_skipped": skipped, "errors": errors,
                "coverage_pct": cov}
    return {}


def _last_int(pattern: str, text: str) -> int | None:
    matches = re.findall(pattern, text)
    return int(matches[-1]) if matches else None
