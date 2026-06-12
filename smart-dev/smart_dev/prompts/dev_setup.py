"""dev-setup: project discovery and context establishment."""

from __future__ import annotations

from pathlib import Path

from ..tools import analyze_codebase
from ..utils import PathError, resolve_dir

_SIGNALS = {
    "package.json": "Node/JavaScript project",
    "pyproject.toml": "Python (PEP 621) project",
    "requirements.txt": "Python (requirements) project",
    "go.mod": "Go module",
    "Cargo.toml": "Rust crate",
    "pom.xml": "Java/Maven project",
    "Dockerfile": "containerized (Docker)",
    ".git": "git repository",
    "next.config.ts": "Next.js app",
    "next.config.js": "Next.js app",
}


def dev_setup(project_path: str) -> str:
    """Discover a project's structure, stack, and recommend next steps."""
    try:
        root = resolve_dir(project_path)
    except PathError as exc:
        return f"Cannot start: {exc}"

    signals = [desc for name, desc in _SIGNALS.items() if (root / name).exists()]
    analysis = analyze_codebase(str(root), max_files=300)
    langs = ", ".join(f"{k} ({v})" for k, v in analysis["languages"].items()) or "none detected"
    q = analysis["metrics"]["quality_score"]

    next_steps = [f"- `code-review` on `{root}` — top issues are flagged below."]
    if analysis["security_findings"]:
        next_steps.insert(0, f"- ⚠️ `code-review` first: {len(analysis['security_findings'])} security finding(s).")
    next_steps.append(f"- `architecture-analysis` on `{root}` — structure & maintainability.")
    next_steps.append(f"- `run_tests('{root}')` — establish a baseline.")
    if q < 70:
        next_steps.append(f"- `refactor-planning` — quality score is {q}/100.")

    return f"""# Dev setup — `{root.name}`

**Path:** `{root}`
**Detected:** {', '.join(signals) or 'no strong signals'}
**Languages:** {langs}
**Files:** {analysis['files_analyzed']} · **Lines:** {analysis['total_lines']} · **Quality:** {q}/100

## Top issues
{_format_issues(analysis)}

## Recommended workflow
{chr(10).join(next_steps)}

This server's prompts compose the tools (`analyze_codebase`, `run_tests`,
`check_dependencies`, `generate_docs`, `deploy_preview`, `rollback_changes`).
Run `list_assets` anytime to see everything available.
"""


def _format_issues(analysis: dict) -> str:
    counts = analysis.get("issue_counts", {})
    if not counts:
        return "_none detected_"
    return "\n".join(f"- {kind}: {n}" for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]))
