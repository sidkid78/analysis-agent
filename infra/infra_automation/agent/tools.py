"""Fleet tools exposed to the agent as function-calling tools.

Thin wrappers with clean signatures/docstrings (the SDK turns these into the
function declarations the model sees). Each operates on the process-wide
``default_fleet`` and returns a JSON-serializable dict.
"""

from __future__ import annotations

from typing import Any

from ..fleet import backup as _backup
from ..fleet import deployment as _deployment
from ..fleet import logs as _logs
from ..fleet import monitoring as _monitoring
from ..fleet import scaling as _scaling
from ..fleet import secrets as _secrets
from ..fleet.model import FleetError, default_fleet

fleet = default_fleet


def _guard(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except FleetError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # surface to the model rather than crash
        return {"error": f"{type(exc).__name__}: {exc}"}


def monitor_services(
    service_filter: str = "all", metrics: str = "standard", alert_threshold: float = 80.0
) -> dict[str, Any]:
    """Get fleet service health and alerts. Filter by name, environment, tag, or 'all'.
    Call this first to understand the current state. Read-only."""
    return _guard(_monitoring.monitor_services, fleet, service_filter, metrics, alert_threshold)


def analyze_logs(
    log_source: str = "all", time_range: str = "1h", log_level: str = "ERROR", pattern: str = ""
) -> dict[str, Any]:
    """Analyze logs for volume, level breakdown, top patterns, and anomalies.
    time_range: 15m|1h|6h|24h|7d. Read-only."""
    return _guard(_logs.analyze_logs, fleet, log_source, time_range, log_level, pattern)


def fleet_status() -> dict[str, Any]:
    """Full snapshot of fleet state: services, resources, secrets, backups, deployments."""
    return _guard(fleet.snapshot)


def deploy_application(
    app_name: str, environment: str = "staging", strategy: str = "rolling", confirm: bool = False
) -> dict[str, Any]:
    """Deploy a service to a new version. PLANS by default; pass confirm=True ONLY
    after the user approves. Strategy: rolling|blue_green|canary."""
    return _guard(_deployment.deploy_application, fleet, app_name, environment, strategy, confirm)


def scale_resources(
    resource_type: str, target_capacity: int, confirm: bool = False
) -> dict[str, Any]:
    """Change a resource's capacity. PLANS by default; pass confirm=True ONLY after
    the user approves. Resource: compute|storage|network|database|cache."""
    return _guard(_scaling.scale_resources, fleet, resource_type, target_capacity, confirm)


def backup_data(
    data_source: str, backup_type: str = "incremental", retention_days: int = 30, confirm: bool = False
) -> dict[str, Any]:
    """Back up a data source. PLANS by default; pass confirm=True ONLY after the
    user approves. Type: full|incremental|differential."""
    return _guard(_backup.backup_data, fleet, data_source, backup_type, retention_days, confirm)


def rotate_secrets(
    secret_type: str = "all", environment: str = "all", force: bool = False, confirm: bool = False
) -> dict[str, Any]:
    """Rotate due credentials. PLANS by default; pass confirm=True ONLY after the
    user approves. force=True rotates all matched, not just overdue ones."""
    return _guard(_secrets.rotate_secrets, fleet, secret_type, environment, force, confirm)


TOOLS = [
    monitor_services,
    analyze_logs,
    fleet_status,
    deploy_application,
    scale_resources,
    backup_data,
    rotate_secrets,
]
TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS}
