"""disaster-recovery: review backups and plan recovery against an RTO target."""

from __future__ import annotations

from ..fleet.model import Fleet


def disaster_recovery_prompt(fleet: Fleet, scenario: str, rto_target: str = "4h") -> str:
    backups = sorted(fleet.backups, key=lambda b: b.created_at, reverse=True)
    sources = sorted({b.data_source for b in backups})
    # Critical data sources we'd expect coverage for.
    critical_sources = {"payments-db", "auth-db"}
    uncovered = sorted(critical_sources - set(sources))

    lines = [
        f"# Disaster recovery — {scenario}",
        "",
        f"RTO target: **{rto_target}**. {len(backups)} backups across "
        f"{len(sources)} data source(s).",
        "",
        "## Backup coverage",
    ]
    if backups:
        for b in backups[:8]:
            lines.append(
                f"- **{b.data_source}** — {b.backup_type}, {b.size_gb}GB, "
                f"{'verified' if b.verified else 'UNVERIFIED'}, {b.created_at}"
            )
    else:
        lines.append("- No backups exist — this is a critical gap.")

    if uncovered:
        lines += ["", "## Gaps (no recent backup)"]
        for src in uncovered:
            lines.append(f"- **{src}** — create one: `backup_data('{src}', 'full', confirm=true)`")

    lines += [
        "",
        "## Recovery plan",
        "1. Declare the scenario and freeze writes to affected stores.",
        "2. Restore from the most recent **verified** backup per data source.",
        "3. Replay deltas since the backup if available (incremental/differential).",
        "4. Run `infra-health-check()` to confirm services recover.",
        "5. Validate against the RTO — escalate if recovery will exceed it.",
        "",
        "Before any risky change, take a fresh backup of critical stores first.",
    ]
    return "\n".join(lines)
