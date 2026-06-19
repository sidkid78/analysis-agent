"""Tests for the deterministic fleet core."""

from __future__ import annotations

import pytest

from infra_automation.fleet.model import Fleet, FleetError, _derive_status


@pytest.fixture
def fleet() -> Fleet:
    return Fleet()


def test_seeded_topology(fleet: Fleet):
    assert len(fleet.services) == 7
    assert len(fleet.resources) == 5
    assert "api-gateway" in fleet.services
    # seeded backups + secrets present
    assert any(b.data_source == "payments-db" for b in fleet.backups)
    assert "db-root-password" in fleet.secrets


def test_metrics_are_deterministic():
    a, b = Fleet(), Fleet()
    for name in a.services:
        assert a.services[name].cpu_percent == b.services[name].cpu_percent
        assert a.services[name].latency_ms == b.services[name].latency_ms


def test_status_derivation():
    assert _derive_status(40, 50, 0.5) == "healthy"
    assert _derive_status(85, 50, 0.5) == "degraded"
    assert _derive_status(40, 50, 3.0) == "degraded"
    assert _derive_status(95, 50, 0.5) == "down"


def test_search_is_degraded_for_demos(fleet: Fleet):
    # The seed deliberately nudges 'search' into trouble (high error rate).
    assert fleet.service("search").status == "degraded"


def test_select_services_filters(fleet: Fleet):
    assert len(fleet.select_services("all")) == 7
    assert [s.name for s in fleet.select_services("api-gateway")] == ["api-gateway"]
    prod = fleet.select_services("production")
    assert all(s.environment == "production" for s in prod) and len(prod) == 5
    critical = fleet.select_services("critical")
    assert {s.name for s in critical} == {"api-gateway", "auth-service", "payments"}


def test_select_services_no_match_raises(fleet: Fleet):
    with pytest.raises(FleetError):
        fleet.select_services("nope")


def test_unknown_service_raises(fleet: Fleet):
    with pytest.raises(FleetError):
        fleet.service("ghost")


def test_secrets_filtering_and_due(fleet: Fleet):
    overdue = [s for s in fleet.secrets_of() if s.due]
    assert {s.name for s in overdue} == {"db-root-password", "staging-api-key"}
    api_keys = fleet.secrets_of("api_keys")
    assert all(s.kind == "api_keys" for s in api_keys)
    prod = fleet.secrets_of("all", "production")
    assert all(s.environment == "production" for s in prod)


def test_snapshot_is_json_serializable(fleet: Fleet):
    import json

    snap = fleet.snapshot()
    json.dumps(snap)  # must not raise
    assert {"services", "resources", "secrets", "backups", "deployments"} <= snap.keys()


def test_reset_restores_topology(fleet: Fleet):
    fleet.services["api-gateway"].replicas = 99
    fleet.tick()
    fleet.reset()
    assert fleet.services["api-gateway"].replicas == 6
    assert fleet.clock == 0
