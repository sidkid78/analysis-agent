"""backup_data: plan-by-default backups appended to the fleet's backup history."""

from __future__ import annotations

import re
from typing import Any

from .model import BackupRecord, Fleet, _now, _unit

_TYPES = ("full", "incremental", "differential")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "data"


def _estimated_size_gb(data_source: str, backup_type: str) -> float:
    base = 5 + 95 * _unit(data_source, "size")  # 5–100 GB full footprint
    factor = {"full": 1.0, "differential": 0.35, "incremental": 0.08}[backup_type]
    return round(base * factor, 1)


def backup_data(
    fleet: Fleet,
    data_source: str,
    backup_type: str = "incremental",
    retention_days: int = 30,
    confirm: bool = False,
) -> dict[str, Any]:
    """Plan (default) or execute a backup. Pass confirm=True to create it.

    Executing appends a verified ``BackupRecord`` to the fleet's history.
    """
    if not data_source.strip():
        from .model import FleetError

        raise FleetError("data_source is required.")
    backup_type = backup_type if backup_type in _TYPES else "incremental"
    retention = int(max(1, min(3650, retention_days)))
    size = _estimated_size_gb(data_source, backup_type)

    if not confirm:
        return {
            "operation": "backup",
            "planned": True,
            "data_source": data_source,
            "backup_type": backup_type,
            "retention_days": retention,
            "estimated_size_gb": size,
            "existing_backups": sum(1 for b in fleet.backups if b.data_source == data_source),
            "confirm_hint": "Call again with confirm=true to create this backup.",
        }

    fleet.tick()
    record = BackupRecord(
        backup_id=f"bkp-{_slug(data_source)}-{fleet.clock:04d}",
        data_source=data_source,
        backup_type=backup_type,
        size_gb=size,
        retention_days=retention,
        verified=True,
        created_at=_now(),
    )
    fleet.backups.append(record)
    return {
        "operation": "backup",
        "planned": False,
        "backup": record.to_dict(),
        "total_backups": len(fleet.backups),
    }
