"""Generate Markdown API docs from source.

Python gets real AST extraction (modules, classes, functions, signatures,
docstrings). Other languages get a best-effort function listing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..languages import FUNCTION_PATTERNS, SKIP_DIRS, detect_language
from ..utils import get_logger, resolve_dir

log = get_logger(__name__)


def generate_docs(path: str, output_path: str = "", max_files: int = 200) -> dict[str, Any]:
    """Generate Markdown documentation for a directory of source files.

    Args:
        path: Project/source directory.
        output_path: If set, also write the Markdown to this file.
        max_files: Cap on files documented.
    """
    root = resolve_dir(path)
    sections: list[str] = [f"# API Documentation — {root.name}", ""]
    symbol_count = 0
    files_done = 0

    for p in sorted(root.rglob("*")):
        if files_done >= max_files:
            break
        if any(part in SKIP_DIRS for part in p.parts) or not p.is_file():
            continue
        language = detect_language(p.suffix)
        if not language:
            continue
        rel = p.relative_to(root).as_posix()
        if language == "Python":
            md, n = _python_doc(p, rel)
        else:
            md, n = _pattern_doc(p, rel, language)
        if n:
            sections.append(md)
            symbol_count += n
            files_done += 1

    markdown = "\n".join(sections).strip() + "\n"
    written = None
    if output_path:
        out = Path(output_path).expanduser()
        out.write_text(markdown, encoding="utf-8")
        written = str(out)

    return {
        "root": str(root),
        "files_documented": files_done,
        "symbols": symbol_count,
        "written_to": written,
        "markdown": markdown if not written else markdown[:4000],
    }


def _python_doc(path: Path, rel: str) -> tuple[str, int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return "", 0
    lines = [f"## `{rel}`", ""]
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        lines += [mod_doc.strip().splitlines()[0], ""]
    count = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(_fn_md(node))
            count += 1
        elif isinstance(node, ast.ClassDef):
            lines.append(f"### class `{node.name}`")
            cd = ast.get_docstring(node)
            if cd:
                lines.append(f"> {cd.strip().splitlines()[0]}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append(_fn_md(item, indent="  "))
                    count += 1
            count += 1
            lines.append("")
    return "\n".join(lines) + "\n", count


def _fn_md(node: ast.AST, indent: str = "") -> str:
    name = node.name  # type: ignore[attr-defined]
    args = ", ".join(a.arg for a in node.args.args)  # type: ignore[attr-defined]
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    head = f"{indent}- **`{name}({args})`**"
    return head + (f" — {doc.strip().splitlines()[0]}" if doc else "")


def _pattern_doc(path: Path, rel: str, language: str) -> tuple[str, int]:
    patterns = FUNCTION_PATTERNS.get(language)
    if not patterns:
        return "", 0
    text = path.read_text(encoding="utf-8", errors="replace")
    names: list[str] = []
    for pat in patterns:
        names.extend(re.findall(pat, text))
    names = sorted({n for n in names if n})
    if not names:
        return "", 0
    lines = [f"## `{rel}` ({language})", ""]
    lines += [f"- `{n}`" for n in names[:40]]
    lines.append("")
    return "\n".join(lines), len(names)
