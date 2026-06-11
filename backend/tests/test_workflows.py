"""Tests for query, quality, playbooks, and report engine modules."""

from __future__ import annotations

import pandas as pd
import pytest

from quickdata.engine import pdf, playbooks, quality, query, report
from quickdata.engine.store import DatasetError, DatasetStore


@pytest.fixture
def store() -> DatasetStore:
    s = DatasetStore()
    s.load_records(
        "orders",
        [
            {"region": "East", "category": "A", "value": 100, "qty": 1},
            {"region": "East", "category": "B", "value": 200, "qty": 2},
            {"region": "West", "category": "A", "value": 50, "qty": 1},
            {"region": "West", "category": "A", "value": 50, "qty": 1},  # dup-ish
            {"region": "West", "category": "B", "value": 400, "qty": 5},
        ],
    )
    return s


# ----------------------------------------------------------------------- query
def test_query_group_and_aggregate(store):
    res = query.run_query(store, "orders", group_by=["region"], metrics=["value:sum", "count"])
    by_region = {r["region"]: r for r in res["rows"]}
    assert by_region["East"]["value_sum"] == 300
    assert by_region["West"]["count"] == 3


def test_query_filter(store):
    res = query.run_query(store, "orders", filters=["value>=200"])
    assert res["matched_rows"] == 2


def test_query_contains_and_sort(store):
    res = query.run_query(
        store, "orders", group_by=["category"], metrics=["value:mean"], sort_by="value_mean"
    )
    assert res["rows"][0]["category"] in {"A", "B"}


def test_query_bad_column(store):
    with pytest.raises(DatasetError):
        query.run_query(store, "orders", filters=["nope==1"])


# --------------------------------------------------------------------- quality
def test_profile_flags_and_score(store):
    p = quality.profile(store, "orders")
    assert p["duplicate_rows"] == 1
    assert 0 <= p["quality_score"] <= 100
    assert any("duplicate" in i["issue"] for i in p["issues"])


def test_clean_drop_duplicates(store):
    res = quality.clean(store, "orders", ["drop_duplicates"])
    assert res["rows_after"] == res["rows_before"] - 1
    assert store.has("orders_clean")


def test_clean_coerce_and_fill():
    s = DatasetStore()
    s.load_records("d", [{"x": "1"}, {"x": "2"}, {"x": None}])
    res = s and quality.clean(s, "d", ["coerce_numeric:x", "fill_nulls:x:median"])
    cleaned = s.frame("d_clean")
    assert pd.api.types.is_numeric_dtype(cleaned["x"])
    assert cleaned["x"].isna().sum() == 0


# ------------------------------------------------------------------- playbooks
def test_playbook_first_look(store):
    r = playbooks.run(store, "first_look", "orders")
    assert r["sections"]
    assert playbooks.to_markdown(r).startswith("## First Look")


def test_playbook_unknown(store):
    with pytest.raises(DatasetError):
        playbooks.run(store, "nope", "orders")


# ---------------------------------------------------------------------- report
def test_report_markdown_and_html(store):
    rep = report.generate_report(store, "orders")
    assert rep["markdown"].startswith("# Data report")
    assert "<h1>" in rep["html"]


def test_report_to_pdf_bytes(store):
    rep = report.generate_report(store, "orders")
    data = pdf.report_to_pdf(rep)
    assert isinstance(data, (bytes, bytearray))
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000
