"""Infrastructure Automation MCP server: tools + prompts over the shared fleet.

Tools are individual operations; prompts are reusable agentic workflows that
compose tools and guide the next step. In an MCP client (e.g. Claude Code)
prompts surface as ``/infrastructure-automation:<prompt>`` slash commands.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import prompts
from .fleet import backup, deployment, logs, monitoring, scaling, secrets
from .fleet.model import FleetError, default_fleet

mcp = FastMCP("infrastructure-automation")
fleet = default_fleet


def _result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _guard(fn):
    """Turn FleetError into a clean message instead of a stack trace."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FleetError as exc:
            return _result({"error": str(exc)})

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ===================================================================== tools


@mcp.tool()
@_guard
def monitor_services(
    service_filter: str = "all", metrics: str = "standard", alert_threshold: float = 80.0
) -> str:
    """Health of fleet services with alerts. Filter by name, environment, tag, or 'all'."""
    return _result(monitoring.monitor_services(fleet, service_filter, metrics, alert_threshold))


@mcp.tool()
@_guard
def deploy_application(
    app_name: str, environment: str = "staging", strategy: str = "rolling", confirm: bool = False
) -> str:
    """Plan a deployment (default) or apply it with confirm=true. Strategy: rolling|blue_green|canary."""
    return _result(deployment.deploy_application(fleet, app_name, environment, strategy, confirm))


@mcp.tool()
@_guard
def scale_resources(resource_type: str, target_capacity: int, confirm: bool = False) -> str:
    """Plan a capacity change (default) or apply it with confirm=true. Resource: compute|storage|network|database|cache."""
    return _result(scaling.scale_resources(fleet, resource_type, target_capacity, confirm))


@mcp.tool()
@_guard
def backup_data(
    data_source: str, backup_type: str = "incremental", retention_days: int = 30, confirm: bool = False
) -> str:
    """Plan a backup (default) or create it with confirm=true. Type: full|incremental|differential."""
    return _result(backup.backup_data(fleet, data_source, backup_type, retention_days, confirm))


@mcp.tool()
@_guard
def rotate_secrets(
    secret_type: str = "all", environment: str = "all", force: bool = False, confirm: bool = False
) -> str:
    """Plan secret rotation (default) or apply it with confirm=true. Rotates due secrets (force=true for all)."""
    return _result(secrets.rotate_secrets(fleet, secret_type, environment, force, confirm))


@mcp.tool()
@_guard
def analyze_logs(
    log_source: str = "all", time_range: str = "1h", log_level: str = "ERROR", pattern: str = ""
) -> str:
    """Analyze logs for volume, level breakdown, top patterns, and anomalies. Read-only."""
    return _result(logs.analyze_logs(fleet, log_source, time_range, log_level, pattern))


@mcp.tool()
@_guard
def fleet_status() -> str:
    """Full snapshot of current fleet state (services, resources, secrets, backups, deployments)."""
    return _result(fleet.snapshot())


@mcp.tool()
@_guard
def reset_fleet() -> str:
    """Reset the fleet to its seeded default topology (useful for demos)."""
    fleet.reset()
    return _result({"reset": True, "services": len(fleet.services)})


# =================================================================== prompts


@mcp.prompt("infra-health-check")
def infra_health_check(scope: str = "all") -> str:
    """Assess fleet health and propose next steps."""
    return prompts.infra_health_check_prompt(fleet, scope)


@mcp.prompt("deployment-strategy")
def deployment_strategy(application: str, target_env: str = "production") -> str:
    """Recommend and plan a deployment with a rollback path."""
    return prompts.deployment_strategy_prompt(fleet, application, target_env)


@mcp.prompt("scaling-analysis")
def scaling_analysis(resource_focus: str = "compute", capacity_target: str = "auto") -> str:
    """Capacity planning for a fleet resource."""
    return prompts.scaling_analysis_prompt(fleet, resource_focus, capacity_target)


@mcp.prompt("incident-response")
def incident_response(incident_type: str, severity: str = "medium") -> str:
    """Triage an incident by composing monitoring and log analysis."""
    return prompts.incident_response_prompt(fleet, incident_type, severity)


@mcp.prompt("security-audit")
def security_audit(audit_scope: str = "full", compliance_framework: str = "") -> str:
    """Review credential hygiene and flag overdue secret rotations."""
    return prompts.security_audit_prompt(fleet, audit_scope, compliance_framework)


@mcp.prompt("disaster-recovery")
def disaster_recovery(scenario: str, rto_target: str = "4h") -> str:
    """Review backup coverage and plan recovery against an RTO target."""
    return prompts.disaster_recovery_prompt(fleet, scenario, rto_target)


@mcp.prompt("list-infra-assets")
def list_infra_assets() -> str:
    """Prime the agent with everything this server can do."""
    snap = default_fleet.snapshot()
    return f"""# Infrastructure Automation MCP — capabilities

A deterministic simulated fleet ({len(snap['services'])} services, \
{len(snap['resources'])} resources). Mutating tools plan by default; pass \
confirm=true to apply.

## Tools
- `monitor_services(service_filter, metrics, alert_threshold)` — health + alerts
- `deploy_application(app_name, environment, strategy, confirm)` — version rollout
- `scale_resources(resource_type, target_capacity, confirm)` — capacity change
- `backup_data(data_source, backup_type, retention_days, confirm)` — backups
- `rotate_secrets(secret_type, environment, force, confirm)` — credential rotation
- `analyze_logs(log_source, time_range, log_level, pattern)` — log analysis
- `fleet_status()` / `reset_fleet()` — snapshot / restore defaults

## Prompts (slash commands)
- `infra-health-check(scope)` — health assessment + next steps
- `deployment-strategy(application, target_env)` — strategy + rollback
- `scaling-analysis(resource_focus, capacity_target)` — capacity planning
- `incident-response(incident_type, severity)` — triage runbook
- `security-audit(audit_scope, compliance_framework)` — secret hygiene
- `disaster-recovery(scenario, rto_target)` — backup review + recovery plan

Start with `infra-health-check()`.
"""


def main() -> None:
    """Console entry point. Runs over stdio for MCP clients like Claude Code."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
