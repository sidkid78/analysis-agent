"""code-review: multi-step review workflow with quality gates."""

from __future__ import annotations

from pathlib import Path

from ..tools import analyze_codebase, run_linter
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

    lint = run_linter(str(root))
    lint_findings = lint.get("findings", [])
    lint_errors = lint.get("by_severity", {}).get("error", 0)

    gate = "BLOCK" if sec else ("WARN" if q < 70 or issues or lint_errors else "PASS")
    lines = [
        f"# Code review — `{root.name}`",
        "",
        f"**Quality gate: {gate}**  ·  score {q}/100  ·  {len(issues)} issue(s)  ·  "
        f"{len(sec)} security finding(s)  ·  {lint.get('finding_count', 0)} lint finding(s)",
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

    lines += ["", "## Linters"]
    linters = lint.get("linters", [])
    if linters:
        statuses = ", ".join(f"{r['tool']} ({r.get('status', '?')})" for r in linters)
        lines.append(f"_ran: {statuses}_")
    if lint_findings:
        for f in lint_findings[:12]:
            code = f" `{f['code']}`" if f.get("code") else ""
            lines.append(f"- **{f['severity']}** `{_rel(f['file'], root)}:{f.get('line', '?')}` "
                         f"— {f['tool']}{code}: {f['message']}")
    elif not linters:
        lines.append("_no linters available (install `ruff`, or add an ESLint config)_")
    else:
        lines.append("_no lint findings_")

    hot = a["metrics"]["complexity_hotspots"]
    if hot:
        lines += ["", "## Complexity hotspots (review carefully)"]
        for h in hot:
            lines.append(f"- `{_rel(h['path'], root)}` — max complexity {h['max_complexity']}")

    lines += [
        "",
        "## Review checklist",
        "1. Resolve all 🔴 security findings before merge.",
        "2. Clear linter errors — `run_linter` (add `typecheck=true` for mypy/tsc).",
        "3. Remove debug statements; address bare/swallowed exceptions.",
        "4. Confirm tests cover changed code — `run_tests` next.",
        "5. Audit dependencies — `check_dependencies`.",
        "6. For risky areas, follow up with `refactor-planning`.",
    ]
    return "\n".join(lines)


def _rel(path: str, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return path
