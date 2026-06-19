"""Engine tests against synthetic in-memory datasets.

Self-contained (does not read ``data/``) so tests are independent of whatever
sample files happen to be present.
"""

from __future__ import annotations

import random

import pytest

from quickdata.engine import analysis, charts, quality, sql, transform
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


def test_sql_select_group_by(store: DatasetStore):
    result = sql.run_sql(
        store, "SELECT region, COUNT(*) AS n FROM ecom GROUP BY region ORDER BY n DESC"
    )
    assert result["columns"] == ["region", "n"]
    assert sum(r["n"] for r in result["rows"]) == store.info("ecom").rows
    # counts must be plain ints, not numpy scalars
    for r in result["rows"]:
        assert isinstance(r["n"], int)
        assert isinstance(r["region"], str)


def test_sql_cross_dataset(store: DatasetStore):
    # Both datasets are registered by default, so one query can touch both.
    result = sql.run_sql(
        store,
        "SELECT (SELECT COUNT(*) FROM ecom) AS e, (SELECT COUNT(*) FROM survey) AS s",
    )
    assert set(result["tables"]) == {"ecom", "survey"}
    row = result["rows"][0]
    assert row["e"] == store.info("ecom").rows
    assert row["s"] == store.info("survey").rows


def test_sql_limit_caps_rows(store: DatasetStore):
    result = sql.run_sql(store, "SELECT * FROM ecom", datasets=["ecom"], limit=5)
    assert result["result_rows"] == store.info("ecom").rows
    assert result["returned_rows"] == 5
    assert len(result["rows"]) == 5


def test_sql_rejects_writes(store: DatasetStore):
    for stmt in ("DROP TABLE ecom", "DELETE FROM ecom", "UPDATE ecom SET region='x'"):
        with pytest.raises(DatasetError):
            sql.run_sql(store, stmt)


def test_sql_bad_dataset(store: DatasetStore):
    with pytest.raises(DatasetError):
        sql.run_sql(store, "SELECT * FROM nope", datasets=["nope"])


def test_sql_empty_query(store: DatasetStore):
    with pytest.raises(DatasetError):
        sql.run_sql(store, "   ")


def test_sql_with_cte_allowed(store: DatasetStore):
    result = sql.run_sql(
        store,
        "WITH big AS (SELECT * FROM ecom WHERE order_value > 100) "
        "SELECT COUNT(*) AS n FROM big",
        datasets=["ecom"],
    )
    assert result["rows"][0]["n"] >= 0


def test_transform_is_non_destructive(store: DatasetStore):
    out = transform.transform_column(store, "ecom", "order_value", "normalize")
    assert out["transformed_dataset"] == "ecom_transformed"
    # original untouched, new dataset created
    assert store.frame("ecom")["order_value"].max() > 1.0
    assert store.frame("ecom_transformed")["order_value"].max() <= 1.0 + 1e-9


def test_transform_into_explicit_target(store: DatasetStore):
    out = transform.transform_column(
        store, "ecom", "region", "uppercase", into="ecom_up"
    )
    assert out["transformed_dataset"] == "ecom_up"
    assert store.frame("ecom_up")["region"].iloc[0].isupper()


def test_transform_bin_adds_column(store: DatasetStore):
    out = transform.transform_column(
        store, "ecom", "order_value", "bin", params={"bins": 4}
    )
    assert "order_value_binned" in out["new_columns"]
    assert "order_value_binned" in store.frame("ecom_transformed").columns


def test_transform_mean_fill_rejects_text(store: DatasetStore):
    with pytest.raises(DatasetError):
        transform.transform_column(store, "ecom", "region", "fill_missing",
                                   params={"method": "mean"})


def test_transform_bad_column(store: DatasetStore):
    with pytest.raises(DatasetError):
        transform.transform_column(store, "ecom", "nope", "to_numeric")


def test_transform_unknown_operation(store: DatasetStore):
    with pytest.raises(DatasetError):
        transform.transform_column(store, "ecom", "order_value", "frobnicate")


def test_add_column_eval(store: DatasetStore):
    out = transform.add_column(store, "ecom", "doubled", "order_value * 2", into="ecom2")
    df = store.frame("ecom2")
    assert "doubled" in df.columns
    assert abs(df["doubled"].iloc[0] - df["order_value"].iloc[0] * 2) < 1e-9


def test_add_column_bad_expression(store: DatasetStore):
    with pytest.raises(DatasetError):
        transform.add_column(store, "ecom", "x", "no_such_col + 1")


def test_filter_rows_keep_and_drop(store: DatasetStore):
    kept = transform.filter_rows(store, "ecom", "order_value > 100", into="hi")
    dropped = transform.filter_rows(store, "ecom", "order_value > 100", keep=False, into="lo")
    assert kept["rows_after"] + dropped["rows_after"] == store.info("ecom").rows
    assert store.frame("hi")["order_value"].min() > 100


def test_filter_rows_bad_condition(store: DatasetStore):
    with pytest.raises(DatasetError):
        transform.filter_rows(store, "ecom", "this is not valid ===")


def test_rename_columns(store: DatasetStore):
    out = transform.rename_columns(store, "ecom", {"region": "area"}, into="ecom_r")
    assert "area" in store.frame("ecom_r").columns
    assert "region" not in store.frame("ecom_r").columns
    # source unchanged
    assert "region" in store.frame("ecom").columns


def test_rename_columns_missing(store: DatasetStore):
    with pytest.raises(DatasetError):
        transform.rename_columns(store, "ecom", {"nope": "x"})


def test_clean_new_tokens():
    s = DatasetStore()
    s.load_records(
        "messy",
        [
            {"keep": 1, "const": "x", "junk": "N/A", "name": " Alice "},
            {"keep": 2, "const": "x", "junk": "", "name": "Bob"},
            {"keep": 2, "const": "x", "junk": "  ", "name": "Bob "},
        ],
    )
    out = quality.clean(
        s,
        "messy",
        ["standardize_missing", "strip_whitespace", "drop_constant", "drop_empty:0.5"],
    )
    cleaned = s.frame(out["cleaned_dataset"])
    assert "const" not in cleaned.columns  # constant column dropped
    assert "junk" not in cleaned.columns  # all-missing after standardize -> dropped
    assert cleaned["name"].tolist() == ["Alice", "Bob", "Bob"]  # whitespace trimmed


def test_clean_unknown_token_still_rejected(store: DatasetStore):
    with pytest.raises(DatasetError):
        quality.clean(store, "ecom", ["frobnicate"])
