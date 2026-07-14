"""Apply automated dependency vulnerability fixes (``npm``/``pnpm audit fix``).

The read-only inventory + audit lives in :func:`check_dependencies`; this is its
mutating sibling. Like ``rollback_changes`` it **plans by default** and only
touches ``package.json`` / the lockfile / ``node_modules`` when called with
``confirm=True``. npm supports a real ``--dry-run``, so the plan is an exact
preview; pnpm has no dry-run, so its plan is the current audit and a note.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils import get_logger, resolve_dir, run_command, which

log = get_logger(__name__)


def fix_dependencies(path: str, confirm: bool = False, force: bool = False) -> dict[str, Any]:
    """Plan (or, with confirm, apply) ``npm``/``pnpm audit fix`` for a JS project.

    Args:
        path: Project directory (must contain package.json).
        confirm: If False (default), return a preview only. If True, actually run
            the fix, mutating package.json / lockfile / node_modules.
        force: npm only — allow SemVer-major updates (``npm audit fix --force``).
            Can introduce breaking changes; off by default.
    """
    root = resolve_dir(path)
    pkg = root / "package.json"
    if not pkg.exists():
        return {"error": f"No package.json in {root} — audit fix applies to npm/pnpm projects only."}

    pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
    if not which(pm):
        return {"error": f"{pm} is not installed or not on PATH."}

    base = {"project": str(root), "package_manager": pm}

    if not confirm:
        return {**base, **_plan(root, pm, force)}

    return {**base, **_apply(root, pm, force)}


# ---------------------------------------------------------------------- plan


def _plan(root: Path, pm: str, force: bool) -> dict[str, Any]:
    if pm == "npm":
        res = run_command(["npm", "audit", "fix", "--dry-run", "--json"], cwd=root, timeout=180)
        preview = _parse_npm(res)
        note = (
            "Dry run — nothing changed. Call fix_dependencies again with confirm=true to apply."
            if not force
            else "Dry run with force — will allow SemVer-major (possibly breaking) updates on apply."
        )
    else:  # pnpm has no --dry-run for --fix; show the audit that a fix would address
        res = run_command(["pnpm", "audit", "--json"], cwd=root, timeout=180)
        preview = _parse_pnpm_audit(res)
        note = (
            "pnpm has no dry-run; the above is the current audit. Applying runs "
            "`pnpm audit --fix`, which adds overrides to package.json for vulnerable deps."
        )
    return {"status": "plan", **preview, "next": note}


# --------------------------------------------------------------------- apply


def _apply(root: Path, pm: str, force: bool) -> dict[str, Any]:
    if pm == "npm":
        cmd = ["npm", "audit", "fix"]
        if force:
            cmd.append("--force")
    else:
        cmd = ["pnpm", "audit", "--fix"]

    log.info("fix_dependencies applying %s in %s", " ".join(cmd), root)
    res = run_command(cmd, cwd=root, timeout=600)
    lock = "pnpm-lock.yaml" if pm == "pnpm" else "package-lock.json"
    return {
        "status": "applied" if res["ok"] else "failed",
        "command": " ".join(cmd),
        "exit_code": res["exit_code"],
        "output": (res["stdout"] + res["stderr"]).strip()[-1200:],
        "undo_hint": (
            f"This may have edited package.json and {lock}. Review with `git diff`; "
            f"undo with `git checkout -- package.json {lock}` then reinstall."
        ),
    }


# -------------------------------------------------------------------- parsers


def _count(v: Any) -> int:
    """npm reports added/removed/changed as arrays (older) or ints (newer)."""
    if isinstance(v, list):
        return len(v)
    if isinstance(v, int):
        return v
    return 0


def _severity_totals(vulns: Any) -> dict[str, int]:
    if not isinstance(vulns, dict):
        return {}
    return {k: v for k, v in vulns.items() if isinstance(v, int) and k != "total"}


def _parse_npm(res: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(res["stdout"] or "{}")
    except json.JSONDecodeError:
        return {"parse": "unavailable", "note": (res["stderr"] or res["stdout"]).strip()[:200]}
    if not isinstance(data, dict):
        return {"parse": "unavailable"}

    audit = data.get("audit") if isinstance(data.get("audit"), dict) else data
    meta = audit.get("metadata", {}) if isinstance(audit, dict) else {}
    remaining = _severity_totals(meta.get("vulnerabilities"))
    return {
        "would_change": {
            "added": _count(data.get("added")),
            "removed": _count(data.get("removed")),
            "changed": _count(data.get("changed")),
            "updated": _count(data.get("updated")),
        },
        "remaining_vulnerabilities": remaining,
        "remaining_total": sum(remaining.values()),
    }


def _parse_pnpm_audit(res: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(res["stdout"] or "{}")
    except json.JSONDecodeError:
        return {"parse": "unavailable", "note": (res["stderr"] or res["stdout"]).strip()[:200]}
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    vulns = _severity_totals(meta.get("vulnerabilities"))
    return {"vulnerabilities": vulns, "vulnerability_total": sum(vulns.values())}
