"""Tests for the agentic workflow prompts (they compose real tools)."""

from __future__ import annotations

import pytest

from infra_automation import prompts
from infra_automation.fleet.model import Fleet


@pytest.fixture
def fleet() -> Fleet:
    return Fleet()


def test_health_check_flags_degraded(fleet: Fleet):
    md = prompts.infra_health_check_prompt(fleet, "all")
    assert "Infrastructure health" in md
    assert "search" in md  # seeded-degraded service surfaces in alerts


def test_deployment_strategy_recommends_canary_for_critical(fleet: Fleet):
    md = prompts.deployment_strategy_prompt(fleet, "payments", "production")
    assert "canary" in md  # payments is PCI/critical in production
    assert "confirm=true" in md


def test_deployment_strategy_unknown_app(fleet: Fleet):
    md = prompts.deployment_strategy_prompt(fleet, "ghost")
    assert "Cannot plan deployment" in md


def test_scaling_analysis_auto_target(fleet: Fleet):
    md = prompts.scaling_analysis_prompt(fleet, "compute", "auto")
    assert "Scaling analysis" in md and "compute" in md


def test_incident_response_runbook(fleet: Fleet):
    md = prompts.incident_response_prompt(fleet, "latency-spike", "high")
    assert "Runbook" in md and "Incident response" in md


def test_security_audit_flags_overdue(fleet: Fleet):
    md = prompts.security_audit_prompt(fleet, "full")
    assert "db-root-password" in md  # overdue secret
    assert "rotate_secrets" in md


def test_disaster_recovery_plan(fleet: Fleet):
    md = prompts.disaster_recovery_prompt(fleet, "region-outage", "2h")
    assert "Recovery plan" in md and "2h" in md
