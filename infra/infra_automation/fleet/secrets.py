"""rotate_secrets: plan-by-default rotation of due (or forced) credentials."""

from __future__ import annotations

from typing import Any

from .model import Fleet


def rotate_secrets(
    fleet: Fleet,
    secret_type: str = "all",
    environment: str = "all",
    force: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Plan (default) or execute secret rotation. Pass confirm=True to apply.

    By default only secrets past their rotation interval are rotated; force=True
    rotates every matching secret. Executing resets each rotated secret's age.
    """
    matched = fleet.secrets_of(secret_type, environment)
    to_rotate = [s for s in matched if s.due or force]
    skipped = [s for s in matched if not (s.due or force)]

    if not confirm:
        return {
            "operation": "rotate",
            "planned": True,
            "secret_type": secret_type,
            "environment": environment,
            "force": force,
            "candidates": [s.to_dict() for s in matched],
            "will_rotate": [s.name for s in to_rotate],
            "skipped_not_due": [s.name for s in skipped],
            "confirm_hint": "Call again with confirm=true to rotate these secrets.",
        }

    fleet.tick()
    rotated: list[str] = []
    for s in to_rotate:
        s.age_days = 0
        rotated.append(s.name)
    return {
        "operation": "rotate",
        "planned": False,
        "rotated": rotated,
        "skipped_not_due": [s.name for s in skipped],
        "still_due": [s.name for s in fleet.secrets_of() if s.due],
    }
