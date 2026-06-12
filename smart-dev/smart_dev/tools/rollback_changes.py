"""Git-based rollback. Plans by default; only executes with ``confirm=True``.

Uses ``git revert`` (which creates a new commit) rather than destructive
history rewrites like ``git reset --hard``, so a rollback is itself reversible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils import get_logger, resolve_dir, run_command, which

log = get_logger(__name__)


def rollback_changes(path: str, target: str = "HEAD", confirm: bool = False) -> dict[str, Any]:
    """Plan (or, with confirm, perform) a safe git revert of a commit.

    Args:
        path: Repository directory.
        target: Commit-ish to revert (default the latest commit, HEAD).
        confirm: If False (default), return a plan only. If True, run git revert.
    """
    root = resolve_dir(path)
    if not which("git"):
        return {"error": "git is not installed or not on PATH."}
    if not (root / ".git").exists():
        return {"error": f"{root} is not a git repository."}

    recent = run_command(["git", "log", "--oneline", "-8"], cwd=root)
    status = run_command(["git", "status", "--porcelain"], cwd=root)
    dirty = bool(status["stdout"].strip())
    show = run_command(["git", "show", "--stat", "--oneline", target], cwd=root)

    if not show["ok"]:
        return {"error": f"Cannot resolve target '{target}': {show['stderr'].strip()[:160]}"}

    plan = {
        "repository": str(root),
        "target": target,
        "would_revert": "\n".join(show["stdout"].splitlines()[:20]),
        "recent_commits": recent["stdout"].strip().splitlines(),
        "working_tree_dirty": dirty,
    }

    if not confirm:
        plan["status"] = "plan"
        plan["next"] = (
            "Review the change above. To apply, call rollback_changes again with "
            "confirm=true. (Commit or stash local changes first if the tree is dirty.)"
        )
        return plan

    if dirty:
        return {**plan, "status": "blocked",
                "error": "Working tree has uncommitted changes — commit or stash before reverting."}

    log.info("rollback_changes executing revert of %s in %s", target, root)
    revert = run_command(["git", "revert", "--no-edit", target], cwd=root)
    return {
        **plan,
        "status": "reverted" if revert["ok"] else "failed",
        "exit_code": revert["exit_code"],
        "output": (revert["stdout"] + revert["stderr"]).strip()[-500:],
        "undo_hint": "This created a new commit; undo it with `git reset --hard HEAD~1` if needed.",
    }
