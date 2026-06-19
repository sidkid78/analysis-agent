"""infra-health-check: assess fleet health and propose next steps."""

from __future__ import annotations

from ..fleet.model import Fleet
from ..fleet.monitoring import monitor_services


def infra_health_check_prompt(fleet: Fleet, scope: str = "all") -> str:
    r = monitor_services(fleet, scope, "detailed")
    s = r["summary"]
    lines = [
        f"# Infrastructure health — `{scope}`",
        "",
        f"**Overall: {s['overall'].upper()}** — {s['healthy']} healthy / "
        f"{s['degraded']} degraded / {s['down']} down across {s['total']} services.",
        "",
    ]
    if r["alerts"]:
        lines.append("## Alerts")
        for a in r["alerts"]:
            lines.append(f"- **{a['service']}** ({a['severity']}): {', '.join(a['reasons'])}")
    else:
        lines.append("No active alerts. ✅")

    degraded = [x["name"] for x in r["services"] if x["status"] != "healthy"]
    lines += ["", "## Suggested next steps"]
    if degraded:
        lines.append(f"- Triage logs: `analyze_logs('{degraded[0]}', '6h', 'ERROR')`")
        lines.append(f"- If incident-worthy: `incident-response('service-degradation', 'high')`")
        lines.append("- If load-driven: `scaling-analysis('compute')`")
    else:
        lines.append("- Fleet is healthy; review credential hygiene with `security-audit()`.")
    return "\n".join(lines)
