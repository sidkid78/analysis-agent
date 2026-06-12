"""Inventory dependencies from project manifests and (optionally) audit them."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..utils import get_logger, resolve_dir, run_command, which

log = get_logger(__name__)


def check_dependencies(path: str, audit: bool = True) -> dict[str, Any]:
    """List dependencies from requirements/pyproject/package.json and audit them.

    Args:
        path: Project directory.
        audit: If True, run pip-audit / npm audit when available (read-only).
    """
    root = resolve_dir(path)
    manifests: dict[str, list[str]] = {}

    req = root / "requirements.txt"
    if req.exists():
        manifests["requirements.txt"] = _parse_requirements(req)

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        manifests["pyproject.toml"] = _parse_pyproject(pyproject)

    pkg = root / "package.json"
    node_deps: dict[str, str] = {}
    if pkg.exists():
        node_deps = _parse_package_json(pkg)
        manifests["package.json"] = [f"{k}@{v}" for k, v in node_deps.items()]

    total = sum(len(v) for v in manifests.values())
    findings: list[dict[str, Any]] = []
    audit_runs: list[dict[str, Any]] = []
    if audit:
        if manifests.get("requirements.txt") or manifests.get("pyproject.toml"):
            audit_runs.append(_pip_audit(root, findings))
        if pkg.exists():
            audit_runs.append(_npm_audit(root, findings))

    return {
        "project": str(root),
        "manifests": manifests,
        "dependency_count": total,
        "audits": [a for a in audit_runs if a],
        "vulnerabilities": findings,
        "summary": (
            f"{total} dependency declaration(s); "
            f"{len(findings)} vulnerability finding(s)."
            if audit else f"{total} dependency declaration(s) (audit skipped)."
        ),
    }


def _parse_requirements(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            out.append(line)
    return out


def _parse_pyproject(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not m:
        return []
    return [s.strip().strip("'\"") for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))]


def _parse_package_json(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    deps = {}
    for key in ("dependencies", "devDependencies"):
        if isinstance(data.get(key), dict):
            deps.update(data[key])
    return deps


def _pip_audit(root: Path, findings: list) -> dict[str, Any] | None:
    if not which("pip-audit"):
        return {"tool": "pip-audit", "status": "not installed — `pip install pip-audit` to enable"}
    res = run_command(["pip-audit", "-f", "json"], cwd=root, timeout=180)
    try:
        data = json.loads(res["stdout"] or "{}")
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        count = 0
        for dep in deps if isinstance(deps, list) else []:
            for v in dep.get("vulns", []):
                count += 1
                findings.append({"tool": "pip-audit", "package": dep.get("name"),
                                 "id": v.get("id"), "fix": v.get("fix_versions")})
        return {"tool": "pip-audit", "status": "ok", "found": count}
    except (json.JSONDecodeError, AttributeError):
        return {"tool": "pip-audit", "status": "ran", "note": res["stderr"][:200]}


def _npm_audit(root: Path, findings: list) -> dict[str, Any] | None:
    pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
    if not which(pm):
        return {"tool": f"{pm} audit", "status": f"{pm} not installed"}
    res = run_command([pm, "audit", "--json"], cwd=root, timeout=180)
    try:
        data = json.loads(res["stdout"] or "{}")
        meta = data.get("metadata", {}).get("vulnerabilities", {})
        total = sum(v for k, v in meta.items() if isinstance(v, int))
        if total:
            findings.append({"tool": f"{pm} audit", "by_severity": meta})
        return {"tool": f"{pm} audit", "status": "ok", "found": total}
    except (json.JSONDecodeError, AttributeError):
        return {"tool": f"{pm} audit", "status": "ran (no lockfile or no JSON output)"}
