"""Tests for the six fleet tool operations."""

from __future__ import annotations

import pytest

from infra_automation.fleet import backup, deployment, logs, monitoring, scaling, secrets
from infra_automation.fleet.model import Fleet, FleetError


@pytest.fixture
def fleet() -> Fleet:
    return Fleet()


# ---------------------------------------------------------------- monitoring
def test_monitor_summary_and_alerts(fleet: Fleet):
    out = monitoring.monitor_services(fleet, "all", "detailed", alert_threshold=80.0)
    assert out["summary"]["total"] == 7
    # 'search' is seeded degraded -> appears in alerts
    assert any(a["service"] == "search" for a in out["alerts"])
    # detailed level includes error_rate
    assert "error_rate" in out["services"][0]


def test_monitor_threshold_changes_alerts(fleet: Fleet):
    low = monitoring.monitor_services(fleet, "all", alert_threshold=10.0)
    high = monitoring.monitor_services(fleet, "all", alert_threshold=99.0)
    assert len(low["alerts"]) >= len(high["alerts"])


def test_monitor_bad_filter_raises(fleet: Fleet):
    with pytest.raises(FleetError):
        monitoring.monitor_services(fleet, "does-not-exist")


# ---------------------------------------------------------------- deployment
def test_deploy_plans_by_default(fleet: Fleet):
    out = deployment.deploy_application(fleet, "api-gateway", "production", "canary")
    assert out["planned"] is True
    assert out["from_version"] == "2.4.1" and out["to_version"] == "2.4.2"
    # nothing mutated
    assert fleet.service("api-gateway").version == "2.4.1"
    assert fleet.deployments == []


def test_deploy_executes_on_confirm(fleet: Fleet):
    out = deployment.deploy_application(fleet, "api-gateway", "production", confirm=True)
    assert out["planned"] is False
    assert fleet.service("api-gateway").version == "2.4.2"
    assert len(fleet.deployments) == 1
    assert out["deployment"]["strategy"] == "rolling"


def test_deploy_unknown_app_raises(fleet: Fleet):
    with pytest.raises(FleetError):
        deployment.deploy_application(fleet, "ghost", confirm=True)


# ------------------------------------------------------------------- scaling
def test_scale_plan_projects_utilization(fleet: Fleet):
    before = fleet.resource("compute").utilization
    out = scaling.scale_resources(fleet, "compute", 24)
    assert out["planned"] is True and out["direction"] == "out"
    # scaling out lowers projected utilization, and nothing changed yet
    assert out["projected_utilization"] < before
    assert fleet.resource("compute").capacity == 12


def test_scale_executes_on_confirm(fleet: Fleet):
    out = scaling.scale_resources(fleet, "compute", 6, confirm=True)
    assert out["new_capacity"] == 6 and out["direction"] == "in"
    assert fleet.resource("compute").capacity == 6


def test_scale_unknown_resource_raises(fleet: Fleet):
    with pytest.raises(FleetError):
        scaling.scale_resources(fleet, "quantum", 10)


# -------------------------------------------------------------------- backup
def test_backup_plans_then_creates(fleet: Fleet):
    plan = backup.backup_data(fleet, "orders-db", "full")
    assert plan["planned"] is True and plan["estimated_size_gb"] > 0
    n = len(fleet.backups)
    done = backup.backup_data(fleet, "orders-db", "full", confirm=True)
    assert done["planned"] is False
    assert len(fleet.backups) == n + 1
    assert done["backup"]["data_source"] == "orders-db"


def test_backup_size_is_deterministic(fleet: Fleet):
    a = backup.backup_data(fleet, "orders-db", "full")["estimated_size_gb"]
    b = backup.backup_data(Fleet(), "orders-db", "full")["estimated_size_gb"]
    assert a == b


# ------------------------------------------------------------------- secrets
def test_rotate_plan_lists_due(fleet: Fleet):
    out = secrets.rotate_secrets(fleet, "all", "all")
    assert out["planned"] is True
    assert set(out["will_rotate"]) == {"db-root-password", "staging-api-key"}


def test_rotate_executes_only_due(fleet: Fleet):
    out = secrets.rotate_secrets(fleet, "all", "all", confirm=True)
    assert set(out["rotated"]) == {"db-root-password", "staging-api-key"}
    assert fleet.secrets["db-root-password"].age_days == 0
    assert fleet.secrets["db-root-password"].due is False


def test_rotate_force_rotates_all_matched(fleet: Fleet):
    out = secrets.rotate_secrets(fleet, "api_keys", "all", force=True, confirm=True)
    # both api_keys rotated even though one wasn't due
    assert set(out["rotated"]) == {"stripe-api-key", "staging-api-key"}


# ---------------------------------------------------------------------- logs
def test_analyze_logs_scales_with_time_range(fleet: Fleet):
    short = logs.analyze_logs(fleet, "all", "1h", "ERROR")
    long = logs.analyze_logs(fleet, "all", "24h", "ERROR")
    assert long["total_matched"] > short["total_matched"]
    assert short["by_level"]["INFO"] >= 0  # counted even if below threshold


def test_analyze_logs_flags_degraded_service(fleet: Fleet):
    out = logs.analyze_logs(fleet, "all", "6h", "ERROR")
    assert any(a["service"] == "search" for a in out["anomalies"])
    # top anomaly is the worst offender
    assert out["anomalies"][0]["projected_errors"] >= out["anomalies"][-1]["projected_errors"]


def test_analyze_logs_pattern_filter(fleet: Fleet):
    out = logs.analyze_logs(fleet, "all", "6h", "WARN", pattern="timeout")
    assert all("timeout" in s["message"].lower() for s in out["samples"])


def test_analyze_logs_bad_inputs_raise(fleet: Fleet):
    with pytest.raises(FleetError):
        logs.analyze_logs(fleet, "all", "3y", "ERROR")
    with pytest.raises(FleetError):
        logs.analyze_logs(fleet, "all", "1h", "LOUD")
    with pytest.raises(FleetError):
        logs.analyze_logs(fleet, "all", "1h", "ERROR", pattern="[unclosed")
