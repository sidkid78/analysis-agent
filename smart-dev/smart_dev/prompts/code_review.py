"""code-review: multi-step review workflow with quality gates."""

from __future__ import annotations

from pathlib import Path

from ..tools import analyze_codebase
from ..utils import PathError, resolve_dir


def code_review(project_path: str) -> str:
    """Run a guided code review with quality gates and actionable feedback."""
    try:
        root = resolve_dir(project_path)
    except PathError as exc:
        return f"Cannot review: {exc}"

    a = analyze_codebase(str(root))
    q = a["metrics"]["quality_score"]
    sec = a["security_findings"]
    issues = a["issues"]

    gate = "BLOCK" if sec else ("WARN" if q < 70 or issues else "PASS")
    lines = [
        f"# Code review — `{root.name}`",
        "",
        f"**Quality gate: {gate}**  ·  score {q}/100  ·  {len(issues)} issue(s)  ·  {len(sec)} security finding(s)",
        "",
    ]

    if sec:
        lines += ["## 🔴 Security (must fix)"]
        for s in sec[:10]:
            lines.append(f"- `{_rel(s['file'], root)}:{s['line']}` — {s['message']}")
        lines.append("")

    lines += ["## Findings (by severity)"]
    if issues:
        for i in issues[:15]:
            lines.append(f"- **{i['severity']}** `{_rel(i['file'], root)}:{i['line']}` — {i['kind']}: {i['message']}")
    else:
        lines.append("_no issues flagged_")

    hot = a["metrics"]["complexity_hotspots"]
    if hot:
        lines += ["", "## Complexity hotspots (review carefully)"]
        for h in hot:
            lines.append(f"- `{_rel(h['path'], root)}` — max complexity {h['max_complexity']}")

    lines += [
        "",
        "## Review checklist",
        "1. Resolve all 🔴 security findings before merge.",
        "2. Remove debug statements; address bare/swallowed exceptions.",
        "3. Confirm tests cover changed code — `run_tests` next.",
        "4. Audit dependencies — `check_dependencies`.",
        "5. For risky areas, follow up with `refactor-planning`.",
    ]
    return "\n".join(lines)


def _rel(path: str, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return path
