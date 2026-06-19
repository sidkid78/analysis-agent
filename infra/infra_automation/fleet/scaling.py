"""scale_resources: plan-by-default capacity changes to a fleet resource."""

from __future__ import annotations

from typing import Any

from .model import Fleet


def scale_resources(
    fleet: Fleet,
    resource_type: str,
    target_capacity: int,
    confirm: bool = False,
) -> dict[str, Any]:
    """Plan (default) or execute a capacity change. Pass confirm=True to apply.

    Utilization is recomputed against the new capacity holding current load
    constant — scaling out lowers utilization, scaling in raises it.
    """
    res = fleet.resource(resource_type)  # raises FleetError
    target = int(max(1, min(10_000, target_capacity)))
    current = res.capacity
    direction = "out" if target > current else "in" if target < current else "none"
    # Absolute load stays fixed; utilization tracks it against capacity.
    load = res.utilization * current
    projected_util = round(min(99.9, load / target), 1) if target else 99.9

    if not confirm:
        return {
            "operation": "scale",
            "planned": True,
            "resource_type": res.kind,
            "unit": res.unit,
            "current_capacity": current,
            "target_capacity": target,
            "delta": target - current,
            "direction": direction,
            "current_utilization": res.utilization,
            "projected_utilization": projected_util,
            "confirm_hint": "Call again with confirm=true to apply this scaling.",
        }

    fleet.tick()
    res.capacity = target
    res.utilization = projected_util
    return {
        "operation": "scale",
        "planned": False,
        "resource_type": res.kind,
        "unit": res.unit,
        "previous_capacity": current,
        "new_capacity": target,
        "direction": direction,
        "new_utilization": res.utilization,
    }
