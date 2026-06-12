"""Smart Development Environment — FastMCP server.

Registers the development tools and the workflow prompts. Tools return JSON;
prompts return guided Markdown. Run over stdio for MCP clients.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import prompts as P
from . import tools as T
from .utils import PathError, get_logger

log = get_logger("smart_dev.server")
mcp = FastMCP("smart-dev-env")


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _guard(fn):
    """Convert PathError into a clean message instead of a stack trace."""

    def wrapper(*args, **kwargs):
        try:
            return _json(fn(*args, **kwargs))
        except PathError as exc:
            return _json({"error": str(exc)})

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ===================================================================== tools


@mcp.tool()
@_guard
def analyze_codebase(path: str, max_files: int = 600) -> str:
    """Static analysis: complexity, quality score, issues, and security scan."""
    return T.analyze_codebase(path, max_files=max_files)


@mcp.tool()
@_guard
def run_tests(path: str, timeout: int = 600) -> str:
    """Detect and run the project's test suite (pytest or npm/pnpm test)."""
    return T.run_tests(path, timeout=timeout)


@mcp.tool()
@_guard
def check_dependencies(path: str, audit: bool = True) -> str:
    """Inventory dependencies and (optionally) run pip-audit / npm audit."""
    return T.check_dependencies(path, audit=audit)


@mcp.tool()
@_guard
def generate_docs(path: str, output_path: str = "", max_files: int = 200) -> str:
    """Generate Markdown API docs from source (Python AST + pattern-based)."""
    return T.generate_docs(path, output_path=output_path, max_files=max_files)


@mcp.tool()
@_guard
def deploy_preview(path: str, run_build: bool = False, timeout: int = 600) -> str:
    """Build-readiness check + simulated preview deploy (build gated by run_build)."""
    return T.deploy_preview(path, run_build=run_build, timeout=timeout)


@mcp.tool()
@_guard
def rollback_changes(path: str, target: str = "HEAD", confirm: bool = False) -> str:
    """Plan (or, with confirm=true, perform) a safe git revert of a commit."""
    return T.rollback_changes(path, target=target, confirm=confirm)


# =================================================================== prompts


@mcp.prompt(title="Dev Setup")
def dev_setup(project_path: str) -> str:
    """Discover a project's stack and recommend the next workflow."""
    return P.dev_setup(project_path)


@mcp.prompt(title="Code Review")
def code_review(project_path: str) -> str:
    """Guided code review with quality gates and security checks."""
    return P.code_review(project_path)


@mcp.prompt(title="Architecture Analysis")
def architecture_analysis(project_path: str) -> str:
    """Assess structure, coupling, and maintainability."""
    return P.architecture_analysis(project_path)


@mcp.prompt(title="Debug Investigation")
def debug_investigation(issue: str, project_path: str = "") -> str:
    """Systematic, hypothesis-driven root-cause investigation."""
    return P.debug_investigation(issue, project_path)


@mcp.prompt(title="Refactor Planning")
def refactor_planning(target: str, project_path: str = "") -> str:
    """Plan a safe, reversible refactor with tests and rollback."""
    return P.refactor_planning(target, project_path)


@mcp.prompt(title="Performance Audit")
def performance_audit(project_path: str) -> str:
    """Guided performance audit grounded in complexity hotspots."""
    return P.performance_audit(project_path)


@mcp.prompt(title="List Assets")
def list_assets() -> str:
    """Prime the agent with everything this server offers."""
    return """# Smart Dev Environment — capabilities

A senior-dev pair programmer. **Prompts** are guided workflows that compose the
**tools**; start with a prompt.

## Workflows (prompts)
- `dev_setup(project_path)` — discover stack, surface issues, recommend next steps
- `code_review(project_path)` — quality-gated review + security findings
- `architecture_analysis(project_path)` — structure & maintainability
- `debug_investigation(issue, project_path?)` — root-cause methodology
- `refactor_planning(target, project_path?)` — safe, reversible refactor plan
- `performance_audit(project_path)` — profiling-led optimization pipeline

## Tools
- `analyze_codebase(path)` — complexity, quality score, issues, secrets
- `run_tests(path)` — pytest / npm test with a parsed summary
- `check_dependencies(path)` — manifest inventory + optional audit
- `generate_docs(path)` — Markdown API docs from source
- `deploy_preview(path, run_build?)` — build/health check, simulated preview URL
- `rollback_changes(path, target?, confirm?)` — git revert (plans unless confirm=true)

## Quick start
`dev_setup("C:/path/to/project")` → follow its recommended workflow.
"""


def main() -> None:
    """Console entry point — stdio transport for MCP clients."""
    log.info("starting smart-dev-env MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
