"""deployment-strategy: recommend and plan a deployment with rollback."""

from __future__ import annotations

from ..fleet.deployment import deploy_application
from ..fleet.model import Fleet, FleetError

_WHY = {
    "canary": "critical/PCI service in production — ramp traffic gradually and watch error rate",
    "blue_green": "production service — keep the old version warm for instant rollback",
    "rolling": "non-production or low-risk — replace replicas in batches",
}


def deployment_strategy_prompt(fleet: Fleet, application: str, target_env: str = "production") -> str:
    try:
        svc = fleet.service(application)
    except FleetError as exc:
        return f"Cannot plan deployment: {exc}"

    critical = bool({"critical", "pci"} & set(svc.tags))
    rec = (
        "canary"
        if (target_env == "production" and critical)
        else "blue_green"
        if target_env == "production"
        else "rolling"
    )
    plan = deploy_application(fleet, application, target_env, rec)  # plan only (no confirm)

    lines = [
        f"# Deployment strategy — `{application}` → {target_env}",
        "",
        f"Version **{plan['from_version']} → {plan['to_version']}**, "
        f"{plan['replicas']} replicas, risk **{plan['risk']}**.",
        "",
        f"**Recommended: `{rec}`** — {_WHY[rec]}.",
        "",
        "## Steps",
    ]
    lines += [f"{i}. {step}" for i, step in enumerate(plan["steps"], 1)]
    lines += [
        "",
        "## Rollback",
        f"- Keep **{plan['from_version']}** available; on a failed health check, revert traffic to it.",
        "",
        f"Apply when ready: "
        f"`deploy_application('{application}', '{target_env}', '{rec}', confirm=true)`.",
    ]
    return "\n".join(lines)
