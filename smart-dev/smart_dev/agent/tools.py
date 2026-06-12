"""The smart-dev tools exposed to the agent as function-calling tools.

Thin wrappers with clean signatures/docstrings (the SDK turns these into the
function declarations the model sees). Each returns a JSON-serializable dict.
"""

from __future__ import annotations

from typing import Any

from .. import tools as T
from ..utils import PathError


def _guard(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except PathError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # surface to the model rather than crash
        return {"error": f"{type(exc).__name__}: {exc}"}


def analyze_codebase(path: str, max_files: int = 600) -> dict[str, Any]:
    """Static analysis of a project directory: complexity, quality score, issues,
    and security/secret findings. Call this first to understand a codebase."""
    return _guard(T.analyze_codebase, path, max_files=max_files)


def run_tests(path: str) -> dict[str, Any]:
    """Detect and run the project's test suite (pytest or npm/pnpm test)."""
    return _guard(T.run_tests, path)


def check_dependencies(path: str, audit: bool = True) -> dict[str, Any]:
    """List dependencies from manifests and optionally audit for vulnerabilities."""
    return _guard(T.check_dependencies, path, audit=audit)


def generate_docs(path: str) -> dict[str, Any]:
    """Generate Markdown API documentation from a project's source."""
    return _guard(T.generate_docs, path)


def deploy_preview(path: str, run_build: bool = False) -> dict[str, Any]:
    """Build-readiness/health check with a simulated preview URL. Set run_build
    to actually run the build (slower)."""
    return _guard(T.deploy_preview, path, run_build=run_build)


def rollback_changes(path: str, target: str = "HEAD", confirm: bool = False) -> dict[str, Any]:
    """Plan a safe git revert of a commit. Returns a plan unless confirm=True,
    which actually performs `git revert`. Always plan before confirming."""
    return _guard(T.rollback_changes, path, target=target, confirm=confirm)


TOOLS = [
    analyze_codebase,
    run_tests,
    check_dependencies,
    generate_docs,
    deploy_preview,
    rollback_changes,
]
TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS}
