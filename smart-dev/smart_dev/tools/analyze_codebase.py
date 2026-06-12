"""Static analysis: complexity, quality scoring, and security scanning.

Python files get real AST-based complexity and structure analysis; other
languages use pattern-based heuristics. Files are read concurrently (thread pool
acts as the I/O throttle) and cached by modification time.
"""

from __future__ import annotations

import ast
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..languages import BRANCH_TOKENS, SKIP_DIRS, detect_language
from ..utils import FileCache, get_logger, resolve_dir

log = get_logger(__name__)
_cache = FileCache()

MAX_FILES = 600
MAX_FILE_BYTES = 1_000_000
LONG_FUNCTION_LINES = 60

_BRANCH_RE = re.compile("|".join(BRANCH_TOKENS))
_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_DEBUG_RES = [
    (re.compile(r"\bconsole\.(log|debug)\("), "console statement"),
    (re.compile(r"\bdebugger\b"), "debugger statement"),
    (re.compile(r"\b(pdb|ipdb)\.set_trace\("), "pdb breakpoint"),
    (re.compile(r"\bbinding\.pry\b"), "pry breakpoint"),
    (re.compile(r"\bSystem\.out\.println\("), "stdout print"),
    (re.compile(r"\bvar_dump\("), "var_dump"),
]
_SECRET_RES = [
    (re.compile(r"""(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)\b\s*[:=]\s*['"][^'"\s]{6,}['"]"""), "hardcoded credential"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"), "Google API key"),
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), "Slack token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
]
_SEVERITY_WEIGHT = {"critical": 12, "high": 8, "warning": 3, "info": 1}


def analyze_codebase(path: str, max_files: int = MAX_FILES) -> dict[str, Any]:
    """Analyze a directory tree: complexity, issues, security, quality score.

    Args:
        path: Absolute path to the project/source directory.
        max_files: Safety cap on how many source files to analyze.
    """
    root = resolve_dir(path)
    log.info("analyze_codebase: %s", root)

    files = _collect_files(root, max_files)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda f: _cache.get_or_compute(f, _analyze_file), files))

    languages: dict[str, int] = {}
    total_lines = 0
    all_complexities: list[int] = []
    issues: list[dict[str, Any]] = []
    security: list[dict[str, Any]] = []
    file_summaries: list[dict[str, Any]] = []
    truncated = len(files) >= max_files

    for r in results:
        if r is None:
            continue
        languages[r["language"]] = languages.get(r["language"], 0) + 1
        total_lines += r["lines"]
        all_complexities.extend(r["function_complexities"])
        rel = r["path"]
        for iss in r["issues"]:
            issues.append({**iss, "file": rel})
        for sec in r["security"]:
            security.append({**sec, "file": rel})
        file_summaries.append(
            {
                "path": rel,
                "language": r["language"],
                "lines": r["lines"],
                "max_complexity": r["max_complexity"],
                "issues": len(r["issues"]) + len(r["security"]),
            }
        )

    avg_complexity = round(sum(all_complexities) / len(all_complexities), 2) if all_complexities else 0.0
    hotspots = sorted(file_summaries, key=lambda f: f["max_complexity"], reverse=True)[:5]
    issue_counts: dict[str, int] = {}
    for iss in issues + security:
        issue_counts[iss["kind"]] = issue_counts.get(iss["kind"], 0) + 1

    quality = _quality_score(total_lines, issues, security)
    return {
        "root": str(root),
        "files_analyzed": len(file_summaries),
        "files_truncated": truncated,
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        "total_lines": total_lines,
        "metrics": {
            "avg_function_complexity": avg_complexity,
            "quality_score": quality,
            "complexity_hotspots": hotspots,
        },
        "issue_counts": issue_counts,
        "issues": sorted(issues, key=lambda i: _SEVERITY_WEIGHT.get(i["severity"], 0), reverse=True)[:40],
        "security_findings": security[:40],
        "recommendations": _recommendations(quality, issues, security, avg_complexity),
    }


def _collect_files(root: Path, max_files: int) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if len(out) >= max_files:
            break
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and detect_language(p.suffix):
            try:
                if p.stat().st_size <= MAX_FILE_BYTES:
                    out.append(p)
            except OSError:
                continue
    return out


def _analyze_file(path: Path) -> dict[str, Any] | None:
    language = detect_language(path.suffix)
    if not language:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = text.count("\n") + 1
    rel = path.name if path.parent == path else str(path)
    issues: list[dict[str, Any]] = []
    security: list[dict[str, Any]] = []
    fn_complexities: list[int] = []

    # Text-based scans (all languages).
    for i, line in enumerate(text.splitlines(), start=1):
        if _TODO_RE.search(line):
            issues.append({"line": i, "severity": "info", "kind": "todo", "message": line.strip()[:120]})
        for rx, label in _DEBUG_RES:
            if rx.search(line):
                issues.append({"line": i, "severity": "warning", "kind": "debug-statement", "message": label})
        for rx, label in _SECRET_RES:
            if rx.search(line):
                security.append({"line": i, "severity": "critical", "kind": "secret", "message": label})

    if language == "Python":
        fn_complexities, py_issues = _analyze_python(text)
        issues.extend(py_issues)
    else:
        fn_complexities = [len(_BRANCH_RE.findall(text)) + 1]

    return {
        "path": str(path),
        "language": language,
        "lines": lines,
        "function_complexities": fn_complexities,
        "max_complexity": max(fn_complexities, default=1),
        "issues": issues,
        "security": security,
    }


def _analyze_python(text: str) -> tuple[list[int], list[dict[str, Any]]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], [{"line": exc.lineno or 0, "severity": "high", "kind": "syntax-error", "message": str(exc.msg)}]

    complexities: list[int] = []
    issues: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexities.append(_cyclomatic(node))
            length = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno
            if length > LONG_FUNCTION_LINES:
                issues.append({"line": node.lineno, "severity": "warning", "kind": "long-function",
                               "message": f"{node.name}() is {length} lines"})
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                issues.append({"line": node.lineno, "severity": "warning", "kind": "bare-except",
                               "message": "bare 'except:'"})
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                issues.append({"line": node.lineno, "severity": "warning", "kind": "swallowed-exception",
                               "message": "exception silently passed"})
    return complexities, issues


def _cyclomatic(fn: ast.AST) -> int:
    score = 1
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.IfExp)):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
    return score


def _quality_score(total_lines: int, issues: list, security: list) -> int:
    weight = sum(_SEVERITY_WEIGHT.get(i["severity"], 1) for i in issues + security)
    per_kloc = weight / max(total_lines / 1000, 1)
    return max(0, min(100, round(100 - per_kloc * 2.5)))


def _recommendations(quality: int, issues: list, security: list, avg_complexity: float) -> list[str]:
    recs: list[str] = []
    if security:
        recs.append(f"Address {len(security)} potential secret(s)/security finding(s) immediately.")
    debug = sum(1 for i in issues if i["kind"] == "debug-statement")
    if debug:
        recs.append(f"Remove {debug} debug statement(s) before shipping.")
    longfn = sum(1 for i in issues if i["kind"] == "long-function")
    if longfn:
        recs.append(f"Refactor {longfn} long function(s) for readability.")
    if avg_complexity >= 8:
        recs.append("Average function complexity is high — consider decomposing branchy functions.")
    if quality >= 85 and not security:
        recs.append("Codebase looks healthy. Run tests and a dependency audit to confirm.")
    return recs or ["No major issues detected."]
