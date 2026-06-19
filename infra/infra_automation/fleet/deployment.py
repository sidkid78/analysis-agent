"""deploy_application: plan-by-default deployment of a service to a new version."""

from __future__ import annotations

from typing import Any

from .model import Deployment, Fleet, _now

_STRATEGIES = ("rolling", "blue_green", "canary")


def _bump_version(v: str) -> str:
    parts = v.split(".")
    if parts and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    return f"{v}.1"


def _strategy_steps(strategy: str, replicas: int) -> list[str]:
    if strategy == "blue_green":
        return [
            f"Provision green environment ({replicas} replicas)",
            "Run health checks on green",
            "Switch traffic 100% blue → green",
            "Drain and decommission blue",
        ]
    if strategy == "canary":
        return [
            "Shift 5% of traffic to the new version",
            "Observe error rate and latency",
            "Ramp to 25%, then 50%",
            "Promote to 100% once healthy",
        ]
    # rolling
    batch = max(1, replicas // 3)
    return [
        f"Replace {batch} replica(s) at a time ({replicas} total)",
        "Health-check each batch before continuing",
        "Roll back the batch on failure",
    ]


def deploy_application(
    fleet: Fleet,
    app_name: str,
    environment: str = "staging",
    strategy: str = "rolling",
    confirm: bool = False,
) -> dict[str, Any]:
    """Plan (default) or execute a deployment. Pass confirm=True to apply.

    Planning is non-destructive: it shows the version bump, strategy steps, and
    risk. Executing bumps the service version and records the deployment.
    """
    svc = fleet.service(app_name)  # raises FleetError
    strategy = strategy if strategy in _STRATEGIES else "rolling"
    from_version = svc.version
    to_version = _bump_version(from_version)
    steps = _strategy_steps(strategy, svc.replicas)
    risk = "high" if environment == "production" else "medium" if environment == "staging" else "low"

    if not confirm:
        return {
            "operation": "deploy",
            "planned": True,
            "app_name": app_name,
            "environment": environment,
            "strategy": strategy,
            "from_version": from_version,
            "to_version": to_version,
            "replicas": svc.replicas,
            "risk": risk,
            "steps": steps,
            "confirm_hint": "Call again with confirm=true to apply this deployment.",
        }

    fleet.tick()
    svc.version = to_version
    deployment = Deployment(
        deployment_id=f"dep-{app_name}-{fleet.clock:04d}",
        app_name=app_name,
        environment=environment,
        strategy=strategy,
        from_version=from_version,
        to_version=to_version,
        status="succeeded",
        at=_now(),
    )
    fleet.deployments.append(deployment)
    return {
        "operation": "deploy",
        "planned": False,
        "deployment": deployment.to_dict(),
        "steps": steps,
        "health_check": {"status": svc.status, "error_rate": svc.error_rate},
    }
