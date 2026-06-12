"""Staging 'preview' for a project — local build + health check.

There's no real deploy target, so this performs *local* readiness checks and an
optional build, then returns a simulated preview URL. Running the build is gated
behind ``run_build`` so a preview is fast and side-effect-free by default.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..utils import get_logger, resolve_dir, run_command

log = get_logger(__name__)


def deploy_preview(path: str, run_build: bool = False, timeout: int = 600) -> dict[str, Any]:
    """Build-readiness check + simulated preview deployment for a project.

    Args:
        path: Project directory.
        run_build: If True, actually run the detected build command (slower).
        timeout: Build timeout in seconds.
    """
    root = resolve_dir(path)
    kind, build_cmd, artifact = _detect(root)

    checks: list[dict[str, Any]] = []
    checks.append(_check("project type detected", kind != "unknown", kind))
    checks.append(_check("build command found", build_cmd is not None,
                         " ".join(build_cmd) if build_cmd else "none"))

    build_result = None
    if run_build and build_cmd:
        log.info("deploy_preview build: %s", build_cmd)
        build_result = run_command(build_cmd, cwd=root, timeout=timeout)
        checks.append(_check("build succeeded", build_result["ok"],
                             f"exit {build_result['exit_code']}"))

    if artifact:
        present = (root / artifact).exists()
        checks.append(_check(f"artifact '{artifact}' present", present,
                             "found" if present else "not built yet"))

    healthy = all(c["passed"] for c in checks)
    slug = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    return {
        "project": str(root),
        "project_type": kind,
        "preview_url": f"https://preview-{slug}.smart-dev.local",  # simulated
        "status": "healthy" if healthy else "degraded",
        "build_ran": bool(run_build and build_cmd),
        "checks": checks,
        "build_output_tail": (
            "\n".join((build_result["stdout"] + build_result["stderr"]).splitlines()[-20:])
            if build_result else None
        ),
        "note": "Preview URL is simulated — no remote deployment was performed.",
    }


def _detect(root: Path) -> tuple[str, list[str] | None, str | None]:
    pkg = root / "package.json"
    if pkg.exists():
        pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
        has_build = False
        try:
            has_build = "build" in json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except (json.JSONDecodeError, OSError):
            pass
        artifact = ".next" if (root / "next.config.ts").exists() or (root / "next.config.js").exists() else "dist"
        return "node", ([pm, "run", "build"] if has_build else None), artifact
    if (root / "Dockerfile").exists():
        return "docker", ["docker", "build", "-t", f"{root.name}:preview", "."], None
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python", ["python", "-m", "build"], "dist"
    return "unknown", None, None


def _check(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}
