"""Tests for the smart-dev tools and prompts against the sample project."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from smart_dev import prompts
from smart_dev.tools import (
    analyze_codebase,
    check_dependencies,
    deploy_preview,
    generate_docs,
    rollback_changes,
    run_tests,
)
from smart_dev.utils import PathError

SAMPLE = str(Path(__file__).resolve().parent.parent / "test-data")


def test_analyze_finds_issues_and_secret():
    r = analyze_codebase(SAMPLE)
    assert r["files_analyzed"] >= 2
    assert "Python" in r["languages"]
    kinds = r["issue_counts"]
    assert kinds.get("bare-except")
    assert kinds.get("debug-statement")
    assert any(s["kind"] == "secret" for s in r["security_findings"])
    assert 0 <= r["metrics"]["quality_score"] <= 100


def test_analyze_bad_path():
    with pytest.raises(PathError):
        analyze_codebase(str(Path(SAMPLE) / "does-not-exist"))


def test_generate_docs():
    r = generate_docs(SAMPLE)
    assert r["symbols"] >= 2
    assert "# API Documentation" in r["markdown"]


def test_check_dependencies_no_audit():
    r = check_dependencies(SAMPLE, audit=False)
    assert "dependency_count" in r
    assert "audit skipped" in r["summary"]


def test_run_tests_detects_none():
    # sample project has no test setup
    r = run_tests(SAMPLE)
    assert r["framework"] is None


def test_deploy_preview_is_simulated():
    r = deploy_preview(SAMPLE, run_build=False)
    assert r["preview_url"].endswith(".smart-dev.local")
    assert r["build_ran"] is False
    assert "checks" in r


def test_rollback_requires_git(tmp_path):
    r = rollback_changes(str(tmp_path))
    assert "error" in r  # not a git repo


def test_rollback_plan_in_real_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, capture_output=True)
    (tmp_path / "a.txt").write_text("hello")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
    r = rollback_changes(str(tmp_path))  # plan only
    assert r["status"] == "plan"
    assert "next" in r


def test_dev_setup_prompt_grounds():
    out = prompts.dev_setup(SAMPLE)
    assert out.startswith("# Dev setup")
    assert "Quality:" in out


def test_code_review_prompt_blocks_on_secret():
    out = prompts.code_review(SAMPLE)
    assert "Quality gate: BLOCK" in out  # sample has a hardcoded secret
