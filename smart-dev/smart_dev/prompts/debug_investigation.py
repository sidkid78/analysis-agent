"""debug-investigation: systematic debugging methodology."""

from __future__ import annotations

from ..utils import PathError, resolve_dir


def debug_investigation(issue: str, project_path: str = "") -> str:
    """Provide a structured root-cause investigation plan for a reported issue."""
    scope = ""
    if project_path:
        try:
            root = resolve_dir(project_path)
            scope = f"\n**Scope:** `{root}`\n"
        except PathError as exc:
            scope = f"\n_(path note: {exc})_\n"

    return f"""# Debug investigation — "{issue}"
{scope}
Follow a hypothesis-driven loop; do not change code until you can reproduce.

## 1. Reproduce
- Capture exact steps, environment, and inputs that trigger it.
- Make it deterministic (smallest failing case). If it's flaky, note frequency.

## 2. Observe
- Read the full error/stack trace; identify the first frame in *your* code.
- `analyze_codebase` on the relevant module — look for recent complexity/issues
  near the failure.
- Check logs around the failure timestamp.

## 3. Localize
- Bisect: which commit/change introduced it? (`git log`, `git bisect`).
- Add targeted logging/asserts at the boundary between "works" and "fails".

## 4. Hypothesize → test
- State a single, falsifiable hypothesis for the root cause.
- Make the smallest change that would confirm or refute it.
- `run_tests` to check you haven't moved the problem.

## 5. Fix & guard
- Fix the **root cause**, not the symptom.
- Add a regression test that fails before the fix and passes after.
- If this is production-impacting, consider `rollback_changes` (plan first) to
  restore service while you fix forward.

## Report
Document: reproduction, root cause, fix, and the test that now guards it.
"""
