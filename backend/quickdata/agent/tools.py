"""Function-calling tools exposed to the agent.

These are thin, LLM-friendly wrappers over ``quickdata.engine`` operating on the
process-wide ``default_store`` (shared with the HTTP API, so datasets uploaded
through the UI are visible here). Docstrings and type hints matter: the SDK
turns them into the function declarations the model sees, so keep them clear.
"""

from __future__ import annotations

from typing import Any

from ..config import DATA_DIR
from ..engine import analysis, charts, playbooks, quality, query, report, sql, transform
from ..engine.store import DatasetError, default_store

store = default_store


def list_datasets() -> dict[str, Any]:
    """List datasets currently loaded in memory, with row/column counts.

    Call this first to see what is available before analyzing anything.
    """
    return {"datasets": [i.to_dict() for i in store.list_info()]}


def list_samples() -> dict[str, Any]:
    """List the bundled sample dataset filenames that can be loaded."""
    if not DATA_DIR.exists():
        return {"samples": []}
    names = [
        p.name
        for ext in ("*.json", "*.csv", "*.tsv")
        for p in sorted(DATA_DIR.glob(ext))
    ]
    return {"samples": names}


def load_sample(filename: str, dataset_name: str = "") -> dict[str, Any]:
    """Load a bundled sample dataset by filename (e.g. 'employee_survey.csv').

    Args:
        filename: A filename returned by list_samples.
        dataset_name: Optional name to store it under; defaults to the file stem.
    """
    path = (DATA_DIR / filename).resolve()
    if DATA_DIR.resolve() not in path.parents or not path.exists():
        return {"error": f"Unknown sample '{filename}'. Call list_samples first."}
    name = dataset_name or path.stem
    try:
        return {"loaded": store.load_file(name, path).to_dict()}
    except DatasetError as exc:
        return {"error": str(exc)}


def dataset_breakdown(dataset_name: str) -> dict[str, Any]:
    """Get a dataset's shape, per-column types/null counts, and sample rows."""
    try:
        return analysis.breakdown(store, dataset_name)
    except DatasetError as exc:
        return {"error": str(exc)}


def suggest_analysis(dataset_name: str) -> dict[str, Any]:
    """Get schema-driven suggestions for what analysis to run next."""
    try:
        return analysis.suggest_analysis(store, dataset_name)
    except DatasetError as exc:
        return {"error": str(exc)}


def segment_by_column(dataset_name: str, column: str) -> dict[str, Any]:
    """Group a dataset by a categorical column; counts plus numeric sums/means."""
    try:
        return analysis.segment_by_column(store, dataset_name, column)
    except DatasetError as exc:
        return {"error": str(exc)}


def find_correlations(dataset_name: str, threshold: float = 0.5) -> dict[str, Any]:
    """Find Pearson correlations between numeric columns at/above |threshold|.

    Args:
        dataset_name: The dataset to analyze.
        threshold: Minimum absolute correlation to report (0..1). Default 0.5.
    """
    try:
        return analysis.find_correlations(store, dataset_name, threshold)
    except DatasetError as exc:
        return {"error": str(exc)}


def create_chart(
    dataset_name: str,
    chart_type: str,
    x: str = "",
    y: str = "",
    bins: int = 10,
) -> dict[str, Any]:
    """Build a chart spec for the UI to render.

    Args:
        dataset_name: The dataset to chart.
        chart_type: One of 'bar', 'pie', 'histogram', 'scatter', 'line'.
        x: Column for the x-axis / category (required for most charts).
        y: Column for the y-axis (for scatter/line, and to aggregate bar/pie).
        bins: Bin count for histograms. Default 10.
    """
    try:
        return charts.build_chart(
            store, dataset_name, chart_type, x=x or None, y=y or None, bins=bins
        )
    except DatasetError as exc:
        return {"error": str(exc)}


def run_query(
    dataset_name: str,
    filters: list[str] | None = None,
    group_by: list[str] | None = None,
    metrics: list[str] | None = None,
    sort_by: str = "",
    descending: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Run a flexible filter/group-by/aggregate query over a dataset.

    Args:
        dataset_name: The dataset to query.
        filters: Row filters like ["region==East Coast", "value>100", "name~smith"]
            (operators: == != > >= < <=, and ~ for case-insensitive contains).
        group_by: Columns to group by, e.g. ["region"].
        metrics: Aggregations like ["value:sum", "value:mean", "count"]
            (aggs: count sum mean min max median std nunique).
        sort_by: A column in the result to sort by.
        descending: Sort direction. Default True.
        limit: Max rows to return. Default 50.
    """
    try:
        return query.run_query(
            store, dataset_name, filters, group_by, metrics, sort_by or None, descending, limit
        )
    except DatasetError as exc:
        return {"error": str(exc)}


def run_sql(dataset_name: str, sql_query: str, limit: int = 100) -> dict[str, Any]:
    """Run a read-only SQL query (SELECT/WITH) over loaded datasets; JOINs allowed.

    Every loaded dataset is queryable as a table named after it. Use this for
    joins or SQL the filter/group-by query DSL can't express.

    Args:
        dataset_name: A dataset involved in the query (others are also available).
        sql_query: A single SELECT or WITH statement.
        limit: Max rows returned. Default 100.
    """
    try:
        return sql.run_sql(store, sql_query, limit=limit)
    except DatasetError as exc:
        return {"error": str(exc)}


def transform_column(
    dataset_name: str,
    column: str,
    operation: str,
    params: dict[str, Any] | None = None,
    into: str = "",
) -> dict[str, Any]:
    """Transform a column into a NEW dataset (non-destructive).

    Args:
        dataset_name: The dataset to transform.
        column: The column to operate on.
        operation: One of to_numeric, to_datetime, to_categorical, parse_json,
            extract_pattern, fill_missing, normalize, bin, map_values, split,
            strip, lowercase, uppercase, replace.
        params: Operation options, e.g. {"method": "zscore"} or {"bins": 4}.
        into: New dataset name. Defaults to '<dataset_name>_transformed'.
    """
    try:
        return transform.transform_column(store, dataset_name, column, operation, params, into or None)
    except DatasetError as exc:
        return {"error": str(exc)}


def add_column(dataset_name: str, new_column: str, expression: str, into: str = "") -> dict[str, Any]:
    """Add a computed column from a pandas expression into a new dataset.

    Args:
        dataset_name: The dataset to extend.
        new_column: Name for the new column.
        expression: A pandas eval expression, e.g. "revenue - cost" or "price * qty".
        into: New dataset name. Defaults to '<dataset_name>_transformed'.
    """
    try:
        return transform.add_column(store, dataset_name, new_column, expression, into or None)
    except DatasetError as exc:
        return {"error": str(exc)}


def filter_rows(dataset_name: str, condition: str, keep: bool = True, into: str = "") -> dict[str, Any]:
    """Materialize a row subset into a new dataset via a pandas query condition.

    Args:
        dataset_name: The dataset to filter.
        condition: A pandas query, e.g. "order_value > 100" or "region == 'East Coast'".
        keep: Keep matching rows (True) or drop them (False).
        into: New dataset name. Defaults to '<dataset_name>_transformed'.
    """
    try:
        return transform.filter_rows(store, dataset_name, condition, keep, into or None)
    except DatasetError as exc:
        return {"error": str(exc)}


def rename_columns(dataset_name: str, mapping: dict[str, str], into: str = "") -> dict[str, Any]:
    """Rename columns into a new dataset via an {old: new} mapping (non-destructive).

    Args:
        dataset_name: The dataset to rename columns in.
        mapping: Old-name to new-name mapping.
        into: New dataset name. Defaults to '<dataset_name>_transformed'.
    """
    try:
        return transform.rename_columns(store, dataset_name, mapping, into or None)
    except DatasetError as exc:
        return {"error": str(exc)}


def profile_dataset(dataset_name: str) -> dict[str, Any]:
    """Profile data quality: nulls, duplicates, outliers, type issues, with fixes."""
    try:
        return quality.profile(store, dataset_name)
    except DatasetError as exc:
        return {"error": str(exc)}


def clean_dataset(dataset_name: str, operations: list[str]) -> dict[str, Any]:
    """Apply cleaning operations into a NEW dataset (non-destructive).

    Args:
        dataset_name: The dataset to clean.
        operations: e.g. ["drop_duplicates", "fill_nulls:score:median",
            "coerce_numeric:price", "drop_columns:notes"].
    """
    try:
        return quality.clean(store, dataset_name, operations)
    except DatasetError as exc:
        return {"error": str(exc)}


def trend_analysis(dataset_name: str, date_column: str = "", metric: str = "") -> dict[str, Any]:
    """Analyze a metric's trend over time: direction, percent change, peak/low + a chart.

    Auto-detects a date column and numeric metric when not given; date-like text
    columns are parsed. With no numeric metric, row counts per period are used.

    Args:
        dataset_name: The dataset to analyze.
        date_column: Date/time column to bucket by. Auto-detected if omitted.
        metric: Numeric column to sum per period. Auto-detected if omitted.
    """
    try:
        result = analysis.trend_analysis(
            store, dataset_name, date_column=date_column or None, metric=metric or None
        )
    except DatasetError as exc:
        return {"error": str(exc)}
    # Re-key so the agent streams the chart (it looks for a `charts` list); drop
    # the full per-period series so we don't echo the points back into context.
    result.pop("series", None)
    result["charts"] = [result.pop("chart")]
    return result


def run_playbook(dataset_name: str, playbook: str) -> dict[str, Any]:
    """Run a canned analysis recipe and return report sections + charts.

    Args:
        dataset_name: The dataset to analyze.
        playbook: One of 'first_look', 'data_quality_audit', 'correlation_deep_dive',
            'executive_summary'.
    """
    try:
        return playbooks.run(store, playbook, dataset_name)
    except DatasetError as exc:
        return {"error": str(exc)}


def generate_report(dataset_name: str) -> dict[str, Any]:
    """Generate a full markdown report (overview, quality, correlations) for a dataset."""
    try:
        return report.generate_report(store, dataset_name)
    except DatasetError as exc:
        return {"error": str(exc)}


# The toolset handed to the model. Order is informational only.
TOOLS = [
    list_datasets,
    list_samples,
    load_sample,
    dataset_breakdown,
    suggest_analysis,
    segment_by_column,
    find_correlations,
    create_chart,
    run_query,
    run_sql,
    profile_dataset,
    clean_dataset,
    transform_column,
    add_column,
    filter_rows,
    rename_columns,
    trend_analysis,
    run_playbook,
    generate_report,
]

TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS}


def is_chart_spec(result: dict[str, Any]) -> bool:
    """True if a tool result is a chart spec (has type + data)."""
    return isinstance(result, dict) and "type" in result and "data" in result and "title" in result
