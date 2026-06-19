"""The deterministic in-memory fleet model.

A process-wide ``default_fleet`` holds a coherent, *seeded* topology of services,
resources, secrets, and backups — the infrastructure equivalent of Quick Data's
``default_store``. Everything is deterministic: metrics are derived from a hash
of (entity, clock), so the same fleet state always yields the same readings, and
state only changes when a tool explicitly mutates it. This is an honest
simulation — coherent and testable — not random noise regenerated per call.

No MCP / HTTP / LLM imports live here; this is the pure core.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

ServiceStatus = str  # "healthy" | "degraded" | "down"
Environment = str  # "dev" | "staging" | "production"


class FleetError(Exception):
    """Raised for user-facing fleet problems (unknown service, bad input)."""


# --------------------------------------------------------------------- helpers


def _unit(*parts: Any) -> float:
    """Deterministic pseudo-random float in [0, 1) from the given parts."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(digest[:8], 16) / 0x100000000


def _between(lo: float, hi: float, *seed: Any) -> float:
    return round(lo + (hi - lo) * _unit(*seed), 1)


def _derive_status(cpu: float, memory: float, error_rate: float) -> ServiceStatus:
    """Classify health from metrics — shared by monitoring and the prompts."""
    if cpu >= 92 or memory >= 95 or error_rate >= 5:
        return "down"
    if cpu >= 80 or memory >= 88 or error_rate >= 2:
        return "degraded"
    return "healthy"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ dataclasses


@dataclass
class Service:
    name: str
    environment: Environment
    version: str
    replicas: int
    cpu_percent: float
    memory_percent: float
    error_rate: float  # percent of requests
    latency_ms: float
    tags: list[str] = field(default_factory=list)

    @property
    def status(self) -> ServiceStatus:
        return _derive_status(self.cpu_percent, self.memory_percent, self.error_rate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "environment": self.environment,
            "version": self.version,
            "replicas": self.replicas,
            "status": self.status,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "error_rate": self.error_rate,
            "latency_ms": self.latency_ms,
            "tags": list(self.tags),
        }


@dataclass
class Resource:
    kind: str  # compute | storage | network | database | cache
    capacity: int
    utilization: float  # percent
    unit: str
    auto_scaling: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "capacity": self.capacity,
            "utilization": self.utilization,
            "unit": self.unit,
            "auto_scaling": self.auto_scaling,
        }


@dataclass
class Secret:
    name: str
    kind: str  # api_keys | certificates | passwords | database
    environment: Environment
    age_days: int
    rotation_interval_days: int

    @property
    def due(self) -> bool:
        return self.age_days >= self.rotation_interval_days

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "environment": self.environment,
            "age_days": self.age_days,
            "rotation_interval_days": self.rotation_interval_days,
            "due": self.due,
        }


@dataclass
class BackupRecord:
    backup_id: str
    data_source: str
    backup_type: str
    size_gb: float
    retention_days: int
    verified: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "data_source": self.data_source,
            "backup_type": self.backup_type,
            "size_gb": self.size_gb,
            "retention_days": self.retention_days,
            "verified": self.verified,
            "created_at": self.created_at,
        }


@dataclass
class Deployment:
    deployment_id: str
    app_name: str
    environment: Environment
    strategy: str
    from_version: str
    to_version: str
    status: str
    at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "app_name": self.app_name,
            "environment": self.environment,
            "strategy": self.strategy,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "status": self.status,
            "at": self.at,
        }


# ------------------------------------------------------- seeded default topology

# (name, environment, version, replicas, tags). Metrics are derived from the name
# so the fleet looks varied but reproducible; a couple of services are nudged into
# a degraded state below to make health checks and incident workflows interesting.
_DEFAULT_SERVICES: tuple[tuple[str, str, str, int, list[str]], ...] = (
    ("api-gateway", "production", "2.4.1", 6, ["edge", "critical"]),
    ("auth-service", "production", "1.9.0", 4, ["critical", "security"]),
    ("payments", "production", "3.1.2", 5, ["critical", "pci"]),
    ("search", "production", "0.8.3", 3, ["data"]),
    ("web-frontend", "production", "5.2.0", 8, ["edge"]),
    ("worker", "staging", "1.0.0", 2, ["batch"]),
    ("notifications", "staging", "0.4.1", 2, ["async"]),
)

# (kind, capacity, unit, auto_scaling). Utilization derived from the kind.
_DEFAULT_RESOURCES: tuple[tuple[str, int, str, bool], ...] = (
    ("compute", 12, "instances", True),
    ("storage", 500, "GB", False),
    ("network", 100, "Gbps", True),
    ("database", 8, "nodes", False),
    ("cache", 6, "nodes", True),
)

# (name, kind, environment, age_days, rotation_interval_days).
_DEFAULT_SECRETS: tuple[tuple[str, str, str, int, int], ...] = (
    ("stripe-api-key", "api_keys", "production", 84, 90),
    ("tls-cert-edge", "certificates", "production", 25, 365),
    ("db-root-password", "passwords", "production", 120, 90),  # overdue
    ("auth-db-creds", "database", "production", 45, 90),
    ("staging-api-key", "api_keys", "staging", 210, 90),  # overdue
)


class Fleet:
    """A deterministic, mutable model of a service fleet."""

    def __init__(self) -> None:
        self.clock = 0
        self.services: dict[str, Service] = {}
        self.resources: dict[str, Resource] = {}
        self.secrets: dict[str, Secret] = {}
        self.backups: list[BackupRecord] = []
        self.deployments: list[Deployment] = []
        self.reset()

    # ------------------------------------------------------------- seeding
    def reset(self) -> None:
        """Restore the seeded default topology (used by tests and the UI)."""
        self.clock = 0
        self.deployments = []
        self.services = {
            name: Service(
                name=name,
                environment=env,
                version=version,
                replicas=replicas,
                cpu_percent=_between(28, 78, name, "cpu"),
                memory_percent=_between(40, 82, name, "mem"),
                error_rate=_between(0.0, 1.4, name, "err"),
                latency_ms=_between(18, 160, name, "lat"),
                tags=list(tags),
            )
            for name, env, version, replicas, tags in _DEFAULT_SERVICES
        }
        # Nudge two services into trouble so health/incident flows have signal.
        self.services["search"].error_rate = 3.6
        self.services["search"].latency_ms = 240.0
        self.services["payments"].cpu_percent = 84.0

        self.resources = {
            kind: Resource(
                kind=kind,
                capacity=capacity,
                utilization=_between(35, 78, kind, "util"),
                unit=unit,
                auto_scaling=auto,
            )
            for kind, capacity, unit, auto in _DEFAULT_RESOURCES
        }
        self.secrets = {
            name: Secret(name=name, kind=kind, environment=env,
                         age_days=age, rotation_interval_days=interval)
            for name, kind, env, age, interval in _DEFAULT_SECRETS
        }
        self.backups = [
            BackupRecord(
                backup_id="bkp-payments-db-0001",
                data_source="payments-db",
                backup_type="full",
                size_gb=42.6,
                retention_days=30,
                verified=True,
                created_at=_now(),
            ),
            BackupRecord(
                backup_id="bkp-auth-db-0001",
                data_source="auth-db",
                backup_type="incremental",
                size_gb=3.1,
                retention_days=14,
                verified=True,
                created_at=_now(),
            ),
        ]

    def tick(self) -> int:
        """Advance the fleet clock (used to order and id operations)."""
        self.clock += 1
        return self.clock

    # ----------------------------------------------------------- accessors
    def service(self, name: str) -> Service:
        if name not in self.services:
            raise FleetError(
                f"No service named '{name}'. Known services: "
                f"{', '.join(sorted(self.services)) or '(none)'}."
            )
        return self.services[name]

    def select_services(self, service_filter: str = "all") -> list[Service]:
        """Resolve a filter to services: 'all', an exact name, an environment,
        or a tag. Raises if nothing matches a specific filter."""
        if service_filter in ("", "all", "*"):
            return [self.services[n] for n in sorted(self.services)]
        if service_filter in self.services:
            return [self.services[service_filter]]
        matched = [
            s
            for n, s in sorted(self.services.items())
            if s.environment == service_filter or service_filter in s.tags
        ]
        if not matched:
            raise FleetError(
                f"No services match '{service_filter}'. Use 'all', a service name, "
                f"an environment (dev/staging/production), or a tag."
            )
        return matched

    def resource(self, kind: str) -> Resource:
        if kind not in self.resources:
            raise FleetError(
                f"No resource '{kind}'. Known resources: "
                f"{', '.join(sorted(self.resources))}."
            )
        return self.resources[kind]

    def secrets_of(self, secret_type: str = "all", environment: str = "all") -> list[Secret]:
        out: Iterable[Secret] = self.secrets.values()
        if secret_type not in ("", "all", "*"):
            out = [s for s in out if s.kind == secret_type]
        if environment not in ("", "all", "*"):
            out = [s for s in out if s.environment == environment]
        return sorted(out, key=lambda s: s.name)

    def snapshot(self) -> dict[str, Any]:
        """A full JSON-serializable view of current fleet state."""
        return {
            "clock": self.clock,
            "services": [s.to_dict() for s in self.select_services("all")],
            "resources": [r.to_dict() for r in self.resources.values()],
            "secrets": [s.to_dict() for s in self.secrets_of()],
            "backups": [b.to_dict() for b in self.backups],
            "deployments": [d.to_dict() for d in self.deployments],
        }


# Process-wide fleet shared by all transports in this process.
default_fleet = Fleet()
