"""monitor_services: read-only health monitoring over the fleet."""

from __future__ import annotations

from typing import Any

from .model import Fleet


def monitor_services(
    fleet: Fleet,
    service_filter: str = "all",
    metrics: str = "standard",
    alert_threshold: float = 80.0,
) -> dict[str, Any]:
    """Summarize service health and raise alerts for anything over threshold.

    metrics: 'standard' (status + utilization), 'detailed' (+ error rate, latency,
    version), or 'performance' (+ tags). Read-only — never mutates the fleet.
    """
    services = fleet.select_services(service_filter)  # raises FleetError
    level = metrics if metrics in ("standard", "detailed", "performance") else "standard"
    threshold = float(max(0.0, min(100.0, alert_threshold)))

    rows: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    counts = {"healthy": 0, "degraded": 0, "down": 0}

    for s in services:
        counts[s.status] += 1
        row: dict[str, Any] = {
            "name": s.name,
            "environment": s.environment,
            "status": s.status,
            "cpu_percent": s.cpu_percent,
            "memory_percent": s.memory_percent,
            "replicas": s.replicas,
        }
        if level in ("detailed", "performance"):
            row.update(error_rate=s.error_rate, latency_ms=s.latency_ms, version=s.version)
        if level == "performance":
            row["tags"] = list(s.tags)
        rows.append(row)

        reasons: list[str] = []
        if s.cpu_percent >= threshold:
            reasons.append(f"CPU {s.cpu_percent}% ≥ {threshold}%")
        if s.memory_percent >= threshold:
            reasons.append(f"memory {s.memory_percent}% ≥ {threshold}%")
        if s.error_rate >= 2:
            reasons.append(f"error rate {s.error_rate}%")
        if s.status != "healthy":
            reasons.append(f"status is {s.status}")
        if reasons:
            alerts.append(
                {
                    "service": s.name,
                    "severity": "critical" if s.status == "down" else "warning",
                    "reasons": reasons,
                }
            )

    overall = (
        "down" if counts["down"] else "degraded" if (counts["degraded"] or alerts) else "healthy"
    )
    return {
        "operation": "monitor",
        "service_filter": service_filter,
        "metrics_level": level,
        "alert_threshold": threshold,
        "summary": {"total": len(rows), **counts, "alerting": len(alerts), "overall": overall},
        "services": rows,
        "alerts": alerts,
    }
