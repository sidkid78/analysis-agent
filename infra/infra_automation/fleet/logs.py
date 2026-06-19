"""analyze_logs: deterministic synthetic log analysis derived from fleet state.

Log volumes and error patterns are computed from each service's health (a
degraded service produces proportionally more errors), so the analysis stays
coherent with what ``monitor_services`` reports — and reproducible.
"""

from __future__ import annotations

import re
from typing import Any

from .model import Fleet, FleetError, _unit

_HOURS = {"15m": 0.25, "1h": 1.0, "6h": 6.0, "24h": 24.0, "7d": 168.0}
_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")
_LEVEL_ORD = {lvl: i for i, lvl in enumerate(_LEVELS)}

_TEMPLATES = {
    "DEBUG": "{svc}: cache lookup completed",
    "INFO": "{svc}: handled request in {lat}ms",
    "WARN": "{svc}: elevated latency on upstream call",
    "ERROR": "{svc}: upstream timeout calling dependency",
    "FATAL": "{svc}: worker crashed (out of memory)",
}


def _rate_per_hour(name: str, level: str, error_factor: float) -> float:
    u = _unit(name, level)
    if level == "DEBUG":
        return 30 * u
    if level == "INFO":
        return 90 + 80 * u
    if level == "WARN":
        return (4 + 8 * u) * (1 + error_factor / 4)
    if level == "ERROR":
        return (0.4 + 1.6 * u) * (1 + error_factor)
    return (0.02 + 0.08 * u) * (1 + error_factor)  # FATAL


def analyze_logs(
    fleet: Fleet,
    log_source: str = "all",
    time_range: str = "1h",
    log_level: str = "ERROR",
    pattern: str = "",
) -> dict[str, Any]:
    """Analyze logs for volume, level breakdown, top patterns, and anomalies.

    log_source: 'all', a service name, or a category label. time_range: one of
    15m/1h/6h/24h/7d. log_level: minimum level to count. pattern: optional regex
    matched against sample lines. Read-only.
    """
    if time_range not in _HOURS:
        raise FleetError(f"Unknown time_range '{time_range}'. Use one of: {', '.join(_HOURS)}.")
    level = log_level.upper()
    if level not in _LEVEL_ORD:
        raise FleetError(f"Unknown log_level '{log_level}'. Use one of: {', '.join(_LEVELS)}.")
    regex = None
    if pattern:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise FleetError(f"Invalid regex pattern: {exc}") from exc

    # Scope services: a known service narrows it; otherwise log_source is a label.
    if log_source in fleet.services:
        services = [fleet.service(log_source)]
    else:
        services = fleet.select_services("all")

    hours = _HOURS[time_range]
    min_ord = _LEVEL_ORD[level]

    by_level = {lvl: 0 for lvl in _LEVELS}
    anomalies: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for s in services:
        error_factor = s.error_rate + (2.0 if s.status == "down" else 0.0)
        svc_error_count = 0
        for lvl in _LEVELS:
            count = int(round(_rate_per_hour(s.name, lvl, error_factor) * hours))
            by_level[lvl] += count
            if lvl in ("ERROR", "FATAL"):
                svc_error_count += count
            # one representative sample per service/level at/above the threshold
            if count > 0 and _LEVEL_ORD[lvl] >= min_ord and len(samples) < 60:
                msg = _TEMPLATES[lvl].format(svc=s.name, lat=int(s.latency_ms))
                if regex is None or regex.search(msg):
                    samples.append({"level": lvl, "service": s.name, "message": msg, "count": count})
        if s.status != "healthy" or s.error_rate >= 2:
            anomalies.append(
                {
                    "service": s.name,
                    "status": s.status,
                    "error_rate": s.error_rate,
                    "projected_errors": svc_error_count,
                    "note": f"{s.name} is {s.status}; error volume elevated over {time_range}.",
                }
            )

    total_matched = sum(c for lvl, c in by_level.items() if _LEVEL_ORD[lvl] >= min_ord)
    # Top patterns: the at/above-threshold levels, ranked by volume.
    top_patterns = sorted(
        (
            {"level": lvl, "pattern": _TEMPLATES[lvl].format(svc="<service>", lat="N"), "count": cnt}
            for lvl, cnt in by_level.items()
            if _LEVEL_ORD[lvl] >= min_ord and cnt > 0
        ),
        key=lambda p: p["count"],
        reverse=True,
    )
    anomalies.sort(key=lambda a: a["projected_errors"], reverse=True)

    return {
        "operation": "analyze_logs",
        "log_source": log_source,
        "time_range": time_range,
        "min_level": level,
        "pattern": pattern or None,
        "total_matched": total_matched,
        "by_level": by_level,
        "top_patterns": top_patterns,
        "anomalies": anomalies,
        "samples": samples,
    }
