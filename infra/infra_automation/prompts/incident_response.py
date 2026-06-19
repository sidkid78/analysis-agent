"""incident-response: triage an incident by composing monitoring + log analysis."""

from __future__ import annotations

from ..fleet.logs import analyze_logs
from ..fleet.model import Fleet
from ..fleet.monitoring import monitor_services


def incident_response_prompt(fleet: Fleet, incident_type: str, severity: str = "medium") -> str:
    health = monitor_services(fleet, "all", "detailed")
    affected = [s for s in health["services"] if s["status"] != "healthy"]
    affected.sort(key=lambda s: s.get("error_rate", 0), reverse=True)
    target = affected[0]["name"] if affected else "all"
    log = analyze_logs(fleet, target, "1h", "ERROR")

    lines = [
        f"# Incident response — {incident_type} ({severity})",
        "",
        f"Fleet status: **{health['summary']['overall']}**, "
        f"{len(affected)} service(s) unhealthy, {len(health['alerts'])} alert(s).",
        "",
        "## Likely blast radius",
    ]
    if affected:
        for s in affected:
            lines.append(
                f"- **{s['name']}** — {s['status']}, error rate {s.get('error_rate', 0)}%, "
                f"latency {s.get('latency_ms', 0)}ms"
            )
    else:
        lines.append("- No unhealthy services; this may be external or a false alarm.")

    lines += [
        "",
        f"## Log signal (`{target}`, last 1h, ERROR+)",
        f"- {log['total_matched']} matching entries; "
        f"top pattern: {log['top_patterns'][0]['pattern'] if log['top_patterns'] else 'none'}",
        "",
        "## Runbook",
    ]
    if severity in ("high", "critical"):
        lines.append(f"1. Mitigate now: `scale_resources('compute', <higher>, confirm=true)` if load-driven.")
        lines.append(f"2. If a recent deploy is implicated, roll back via `deployment-strategy('{target}')`.")
        lines.append("3. Open an incident channel and assign an IC.")
    else:
        lines.append(f"1. Watch: re-run `analyze_logs('{target}', '6h', 'ERROR')` to confirm a trend.")
        lines.append("2. Capacity check: `scaling-analysis('compute')`.")
    lines.append("4. After recovery, snapshot state for the post-mortem.")
    return "\n".join(lines)
