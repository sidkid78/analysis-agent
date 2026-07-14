"""Run real linters and type-checkers over a project and normalize their output.

Unlike ``analyze_codebase`` (home-grown AST/regex heuristics), this shells out to
the ecosystem-standard tools when they are installed and parses their structured
output into one common shape:

- **Ruff** (`ruff check`) — Python lint
- **ESLint** (`eslint -f json`) — JS/TS lint
- **mypy** — Python type-check (opt-in via ``typecheck``)
- **tsc --noEmit** — TypeScript type-check (opt-in via ``typecheck``)

If a tool (or its config) is missing, that pass degrades gracefully with a hint
instead of failing. With ``diff_base`` set (e.g. ``"HEAD"``) only files changed vs
that ref are linted. Read-only: tools run in check mode, never --fix.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..utils import get_logger, git_changed_files, resolve_dir, run_command, which

log = get_logger(__name__)

MAX_FINDINGS = 60
_PY_EXTS = {".py", ".pyi"}
_JS_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
_ALL_EXTS = _PY_EXTS | _JS_EXTS
_ESLINT_CONFIGS = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
)
# Skip these dirs when deciding whether a language is even present.
_SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__", ".next"}

# mypy:  path:line:col: severity: message  [code]
_MYPY_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<sev>error|warning|note):\s*(?P<msg>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$"
)
# tsc --pretty false:  path(line,col): error TSxxxx: message
_TSC_RE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<sev>error|warning)\s+(?P<code>TS\d+):\s*(?P<msg>.*)$"
)


def run_linter(
    path: str,
    max_findings: int = MAX_FINDINGS,
    typecheck: bool = False,
    diff_base: str = "",
) -> dict[str, Any]:
    """Lint (and optionally type-check) a project.

    Args:
        path: Absolute path to the project/source directory.
        max_findings: Cap on findings returned (payload safety).
        typecheck: Also run mypy (Python) and ``tsc --noEmit`` (TypeScript).
        diff_base: If set (e.g. ``"HEAD"``), only lint files changed vs this git
            ref (working-tree changes + untracked). tsc always checks the whole
            program (it cannot be scoped to a file subset).
    """
    root = resolve_dir(path)
    log.info("run_linter: %s (typecheck=%s, diff_base=%r)", root, typecheck, diff_base)

    scope: dict[str, Any] = {"mode": "full"}
    py_files: list[str] | None = None
    js_files: list[str] | None = None

    if diff_base:
        changed, err = git_changed_files(root, diff_base, _ALL_EXTS)
        if err:
            return {"project": str(root), "linters": [],
                    "scope": {"mode": "diff", "base": diff_base, "error": err},
                    "message": f"Could not scope to diff vs '{diff_base}': {err}"}
        if not changed:
            return {"project": str(root), "linters": [],
                    "scope": {"mode": "diff", "base": diff_base, "files": 0},
                    "message": f"No changed lintable files vs '{diff_base}'."}
        py_files = [f for f in changed if Path(f).suffix in _PY_EXTS]
        js_files = [f for f in changed if Path(f).suffix in _JS_EXTS]
        scope = {"mode": "diff", "base": diff_base, "files": len(changed)}
        has_py, has_js = bool(py_files), bool(js_files)
    else:
        has_py, has_js = _detect_languages(root)

    runs: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    if has_py:
        runs.append(_run_ruff(root, findings, max_findings, py_files))
        if typecheck:
            runs.append(_run_mypy(root, findings, max_findings, py_files))
    if has_js:
        runs.append(_run_eslint(root, findings, max_findings, js_files))
    if typecheck and (root / "tsconfig.json").exists():
        runs.append(_run_tsc(root, findings, max_findings))

    if not runs:
        return {"project": str(root), "scope": scope, "linters": [],
                "message": "No Python or JS/TS sources found to lint."}

    by_severity: dict[str, int] = {}
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    total = sum(r.get("found", 0) for r in runs)

    return {
        "project": str(root),
        "scope": scope,
        "linters": runs,
        "finding_count": total,
        "by_severity": dict(sorted(by_severity.items())),
        "findings": findings[:max_findings],
        "summary": _summarize(runs, total, by_severity),
    }


# ------------------------------------------------------------------- scoping


def _detect_languages(root: Path) -> tuple[bool, bool]:
    has_py = has_js = False
    for p in root.rglob("*"):
        if has_py and has_js:
            break
        if any(part in _SKIP for part in p.parts) or not p.is_file():
            continue
        if p.suffix in _PY_EXTS:
            has_py = True
        elif p.suffix in _JS_EXTS:
            has_js = True
    return has_py, has_js


# --------------------------------------------------------------------- tools


def _run_ruff(root: Path, findings: list, cap: int, files: list[str] | None) -> dict[str, Any]:
    if not which("ruff"):
        return {"tool": "ruff", "status": "not installed — `pip install ruff` (or `uv tool install ruff`) to enable"}
    targets = files if files else ["."]
    res = run_command(["ruff", "check", "--output-format", "json", *targets], cwd=root, timeout=180)
    try:
        items = json.loads(res["stdout"] or "[]")
    except json.JSONDecodeError:
        return {"tool": "ruff", "status": "ran", "note": (res["stderr"] or res["stdout"])[:200]}
    added = 0
    for it in items:
        if added >= cap:
            break
        loc = it.get("location") or {}
        findings.append({
            "tool": "ruff",
            "file": _rel(it.get("filename", ""), root),
            "line": loc.get("row"),
            "column": loc.get("column"),
            "code": it.get("code"),
            "severity": "error",
            "message": it.get("message", ""),
            "fixable": bool(it.get("fix")),
        })
        added += 1
    fixable = sum(1 for f in findings if f["tool"] == "ruff" and f["fixable"])
    return {"tool": "ruff", "status": "ok", "found": len(items), "returned": added, "fixable": fixable}


def _run_eslint(root: Path, findings: list, cap: int, files: list[str] | None) -> dict[str, Any]:
    if not any((root / c).exists() for c in _ESLINT_CONFIGS):
        return {"tool": "eslint", "status": "no ESLint config found — skipped"}
    pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
    runner = ["pnpm", "exec", "eslint"] if pm == "pnpm" else ["npx", "--no-install", "eslint"]
    if not which(runner[0]):
        return {"tool": "eslint", "status": f"{runner[0]} not installed"}
    targets = files if files else ["."]
    res = run_command([*runner, *targets, "-f", "json"], cwd=root, timeout=240)
    try:
        file_results = json.loads(res["stdout"] or "[]")
    except json.JSONDecodeError:
        return {"tool": "eslint", "status": "ran",
                "note": (res["stderr"] or res["stdout"])[:200] or "no JSON output (eslint not resolvable?)"}
    total = added = fixable = 0
    for fr in file_results:
        for m in fr.get("messages", []):
            total += 1
            if added >= cap:
                continue
            findings.append({
                "tool": "eslint",
                "file": _rel(fr.get("filePath", ""), root),
                "line": m.get("line"),
                "column": m.get("column"),
                "code": m.get("ruleId"),
                "severity": "error" if m.get("severity") == 2 else "warning",
                "message": m.get("message", ""),
                "fixable": bool(m.get("fix")),
            })
            if m.get("fix"):
                fixable += 1
            added += 1
    return {"tool": "eslint", "status": "ok", "found": total, "returned": added, "fixable": fixable}


def _run_mypy(root: Path, findings: list, cap: int, files: list[str] | None) -> dict[str, Any]:
    if not which("mypy"):
        return {"tool": "mypy", "status": "not installed — `pip install mypy` to enable"}
    targets = files if files else ["."]
    res = run_command(
        ["mypy", "--no-color-output", "--no-error-summary", "--show-column-numbers",
         "--show-error-codes", "--hide-error-context", *targets],
        cwd=root, timeout=300,
    )
    output = res["stdout"] + "\n" + res["stderr"]
    total = added = 0
    for line in output.splitlines():
        m = _MYPY_RE.match(line.strip())
        if not m or m.group("sev") == "note":
            continue
        total += 1
        if added >= cap:
            continue
        findings.append({
            "tool": "mypy",
            "file": _rel(m.group("file"), root),
            "line": int(m.group("line")),
            "column": int(m.group("col")) if m.group("col") else None,
            "code": m.group("code"),
            "severity": m.group("sev"),
            "message": m.group("msg"),
            "fixable": False,
        })
        added += 1
    return {"tool": "mypy", "status": "ok", "found": total, "returned": added}


def _run_tsc(root: Path, findings: list, cap: int) -> dict[str, Any]:
    pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
    runner = ["pnpm", "exec", "tsc"] if pm == "pnpm" else ["npx", "--no-install", "tsc"]
    if not which(runner[0]):
        return {"tool": "tsc", "status": f"{runner[0]} not installed"}
    res = run_command([*runner, "--noEmit", "--pretty", "false"], cwd=root, timeout=300)
    output = res["stdout"] + "\n" + res["stderr"]
    total = added = 0
    for line in output.splitlines():
        m = _TSC_RE.match(line.strip())
        if not m:
            continue
        total += 1
        if added >= cap:
            continue
        findings.append({
            "tool": "tsc",
            "file": _rel(m.group("file"), root),
            "line": int(m.group("line")),
            "column": int(m.group("col")),
            "code": m.group("code"),
            "severity": m.group("sev"),
            "message": m.group("msg"),
            "fixable": False,
        })
        added += 1
    status = "ok" if (total or res["exit_code"] == 0) else "ran"
    return {"tool": "tsc", "status": status, "found": total, "returned": added,
            "note": None if status == "ok" else (res["stderr"] or "")[:200] or None}


# --------------------------------------------------------------------- helpers


def _rel(filename: str, root: Path) -> str:
    if not filename:
        return ""
    try:
        return str(Path(filename).resolve().relative_to(root))
    except ValueError:
        return filename


def _summarize(runs: list, total: int, by_severity: dict) -> str:
    ran = [r["tool"] for r in runs if r.get("status") == "ok"]
    skipped = [r["tool"] for r in runs if r.get("status") != "ok"]
    parts = []
    if ran:
        errs = by_severity.get("error", 0)
        warns = by_severity.get("warning", 0)
        parts.append(f"{', '.join(ran)} ran: {total} finding(s) ({errs} error, {warns} warning).")
    if skipped:
        parts.append(f"skipped/degraded: {', '.join(skipped)}.")
    return " ".join(parts) or "No tools ran."
