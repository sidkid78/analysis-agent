"""Engine tests against synthetic in-memory datasets.

Self-contained (does not read ``data/``) so tests are independent of whatever
sample files happen to be present.
"""

from __future__ import annotations

import random

import pytest

from quickdata.engine import analysis, charts
from quickdata.engine.store import DatasetError, DatasetStore


@pytest.fixture
def store() -> DatasetStore:
    rng = random.Random(42)
    categories = ["Electronics", "Sports", "Books"]
    regions = ["East Coast", "West Coast", "Midwest", "South"]
    ecom = [
        {
            "order_id": f"ORD-{i}",
            "product_category": rng.choice(categories),
            "region": rng.choice(regions),
            "order_value": round(rng.uniform(20, 500), 2),
        }
        for i in range(120)
    ]
    # satisfaction grows with tenure -> strong positive correlation
    survey = []
    for i in range(120):
        tenure = round(rng.uniform(0.2, 12.0), 1)
        satisfaction = max(1.0, min(10.0, 4.0 + 0.45 * tenure + rng.gauss(0, 1.0)))
        survey.append(
            {
                "employee_id": f"EMP-{i:03d}",
                "department": rng.choice(["Eng", "Sales", "Support"]),
                "tenure_years": tenure,
                "satisfaction_score": round(satisfaction, 2),
            }
        )

    s = DatasetStore()
    s.load_records("ecom", ecom)
    s.load_records("survey", survey)
    return s


def test_load_and_info(store: DatasetStore):
    info = store.info("ecom")
    assert info.rows > 0
    assert "order_value" in info.columns_of_kind("numerical")
    assert "product_category" in info.columns_of_kind("categorical")


def test_breakdown_is_json_safe(store: DatasetStore):
    b = analysis.breakdown(store, "ecom")
    assert b["rows"] == store.info("ecom").rows
    assert b["sample"]
    # sample values must be plain JSON types (no numpy scalars)
    for row in b["sample"]:
        for v in row.values():
            assert v is None or isinstance(v, (int, float, str, bool))


def test_segment(store: DatasetStore):
    seg = analysis.segment_by_column(store, "ecom", "region")
    assert seg["segments"]
    assert "order_value_sum" in seg["segments"][0]


def test_segment_bad_column(store: DatasetStore):
    with pytest.raises(DatasetError):
        analysis.segment_by_column(store, "ecom", "nope")


def test_correlation_detects_tenure_satisfaction(store: DatasetStore):
    result = analysis.find_correlations(store, "survey", threshold=0.4)
    pairs = {tuple(sorted((p["x"], p["y"]))) for p in result["correlations"]}
    assert ("satisfaction_score", "tenure_years") in pairs


def test_correlation_needs_two_numeric():
    s = DatasetStore()
    s.load_records("tiny", [{"name": "a"}, {"name": "b"}])
    with pytest.raises(DatasetError):
        analysis.find_correlations(s, "tiny")


def test_chart_bar(store: DatasetStore):
    spec = charts.build_chart(store, "ecom", "bar", x="region", y="order_value")
    assert spec["type"] == "bar"
    assert spec["data"]
    assert {"label", "value"} <= spec["data"][0].keys()


def test_chart_scatter(store: DatasetStore):
    spec = charts.build_chart(store, "survey", "scatter", x="tenure_years", y="satisfaction_score")
    assert spec["type"] == "scatter"
    assert {"x", "y"} <= spec["data"][0].keys()
