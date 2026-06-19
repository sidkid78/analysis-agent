"""security-audit: credential hygiene review over the fleet's secrets."""

from __future__ import annotations

from ..fleet.model import Fleet


def security_audit_prompt(
    fleet: Fleet, audit_scope: str = "full", compliance_framework: str = ""
) -> str:
    secrets = fleet.secrets_of("all", "all")
    due = [s for s in secrets if s.due]
    aging = [s for s in secrets if not s.due and s.age_days >= 0.8 * s.rotation_interval_days]

    framework = f" ({compliance_framework})" if compliance_framework else ""
    lines = [
        f"# Security audit — {audit_scope}{framework}",
        "",
        f"{len(secrets)} secrets tracked · **{len(due)} overdue** · {len(aging)} aging.",
        "",
    ]
    if due:
        lines.append("## Overdue rotation (act now)")
        for s in due:
            lines.append(
                f"- **{s.name}** ({s.kind}, {s.environment}) — {s.age_days}d old, "
                f"interval {s.rotation_interval_days}d"
            )
        lines += [
            "",
            "Rotate the overdue set: `rotate_secrets('all', 'all', confirm=true)`.",
        ]
    else:
        lines.append("No overdue secrets. ✅")

    if aging:
        lines += ["", "## Aging (rotate soon)"]
        lines += [f"- {s.name} ({s.age_days}/{s.rotation_interval_days}d)" for s in aging]

    lines += [
        "",
        "## Checklist",
        "- Confirm rotation does not break dependents (stagger by environment).",
        "- Verify certificate chains after `tls-cert-*` rotations.",
        "- Re-run this audit after rotating to confirm a clean bill of health.",
    ]
    return "\n".join(lines)
