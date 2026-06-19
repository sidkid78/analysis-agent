"""scaling-analysis: capacity planning for a fleet resource."""

from __future__ import annotations

from ..fleet.model import Fleet, FleetError
from ..fleet.scaling import scale_resources

_TARGET_UTIL = 60.0  # aim to land here after scaling


def scaling_analysis_prompt(
    fleet: Fleet, resource_focus: str = "compute", capacity_target: str = "auto"
) -> str:
    try:
        res = fleet.resource(resource_focus)
    except FleetError as exc:
        return f"Cannot analyze scaling: {exc}"

    if capacity_target == "auto":
        # Capacity needed to bring utilization down to the target band.
        load = res.utilization * res.capacity
        target = max(1, round(load / _TARGET_UTIL))
    else:
        try:
            target = int(capacity_target)
        except ValueError:
            return f"capacity_target must be an integer or 'auto', got '{capacity_target}'."

    plan = scale_resources(fleet, resource_focus, target)  # plan only
    verdict = (
        "scale out — utilization is high"
        if res.utilization >= 75
        else "scale in — capacity is underused"
        if res.utilization <= 40
        else "holding — utilization is healthy"
    )
    lines = [
        f"# Scaling analysis — `{res.kind}`",
        "",
        f"Current: **{res.capacity} {res.unit}** at **{res.utilization}%** utilization "
        f"(auto-scaling {'on' if res.auto_scaling else 'off'}).",
        "",
        f"**Recommendation: {verdict}.**",
        f"- Target **{plan['target_capacity']} {res.unit}** "
        f"(Δ {plan['delta']:+d}) → ~{plan['projected_utilization']}% utilization.",
        "",
        f"Apply when ready: "
        f"`scale_resources('{res.kind}', {plan['target_capacity']}, confirm=true)`.",
    ]
    return "\n".join(lines)
