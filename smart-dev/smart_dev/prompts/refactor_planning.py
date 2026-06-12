"""refactor-planning: safe refactoring workflow with rollback strategy."""

from __future__ import annotations

from pathlib import Path

from ..tools import analyze_codebase
from ..utils import PathError, resolve_dir


def refactor_planning(target: str, project_path: str = "") -> str:
    """Plan a safe refactor of a module/area with tests and rollback in place."""
    grounding = ""
    root = None
    if project_path:
        try:
            root = resolve_dir(project_path)
            a = analyze_codebase(str(root))
            hot = a["metrics"]["complexity_hotspots"][:3]
            grounding = "\n**Current hotspots:**\n" + (
                "\n".join(f"- `{_rel(h['path'], root)}` (complexity {h['max_complexity']})" for h in hot)
                or "- none"
            ) + "\n"
        except PathError as exc:
            grounding = f"\n_(path note: {exc})_\n"

    return f"""# Refactor plan — {target}
{grounding}
Refactoring changes structure **without changing behavior** — so behavior must be
pinned first.

## 1. Establish a safety net
- `run_tests` — green baseline. If coverage is thin around `{target}`, add
  characterization tests that capture current behavior first.
- Commit a clean checkpoint so rollback is trivial.

## 2. Plan in small, reversible steps
- List the specific smells (long functions, duplication, tight coupling).
- Sequence changes so each step keeps tests green and is independently committable.
- Prefer mechanical, well-known moves: extract function, introduce parameter
  object, replace conditional with polymorphism, etc.

## 3. Execute
- One refactor per commit. Run tests after each. Never mix refactor + behavior change.
- Re-run `analyze_codebase` to confirm complexity actually dropped.

## 4. Rollback strategy
- Each step is a commit → revert any single step with `rollback_changes`
  (plan first, then confirm).
- If mid-refactor and broken, revert to the checkpoint rather than pushing through.

## 5. Verify
- Tests green, complexity reduced, behavior unchanged.
- `code-review` the diff before merge.
"""


def _rel(path: str, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return path
