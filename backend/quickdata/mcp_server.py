"""Quick Data MCP server: tools + prompts over the shared analysis engine.

Tools are individual actions. Prompts are reusable agentic workflows that
compose tools and guide the next step — the high-leverage primitive. In an MCP
client (e.g. Claude Code) prompts surface as ``/quick-data:<prompt>`` slash
commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import DATA_DIR
from .engine import analysis, charts, playbooks, quality, query, sql, transform
from .engine.store import DatasetError, default_store

mcp = FastMCP("quick-data")
store = default_store

def _result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _guard(fn):
    """Turn DatasetError into a clean message instead of a stack trace."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DatasetError as exc:
            return _result({"error": str(exc)})

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ===================================================================== tools


@mcp.tool()
@_guard
def load_dataset(file_path: str, dataset_name: str) -> str:
    """Load a JSON or CSV file into memory under a name for later analysis."""
    info = store.load_file(dataset_name, file_path)
    return _result(
        {
            "loaded": info.to_dict(),
            "next": f"Run dataset_first_look('{dataset_name}') or "
            f"dataset_breakdown('{dataset_name}').",
        }
    )


@mcp.tool()
@_guard
def list_datasets() -> str:
    """List all datasets currently loaded in memory with their shape."""
    infos = [i.to_dict() for i in store.list_info()]
    return _result({"datasets": infos, "count": len(infos)})


@mcp.tool()
@_guard
def dataset_breakdown(dataset_name: str) -> str:
    """Shape, per-column types/null counts, and sample rows for a dataset."""
    return _result(analysis.breakdown(store, dataset_name))


@mcp.tool()
@_guard
def suggest_analysis(dataset_name: str) -> str:
    """Suggest next analysis steps based on the dataset's column types."""
    return _result(analysis.suggest_analysis(store, dataset_name))


@mcp.tool()
@_guard
def segment_by_column(dataset_name: str, column: str) -> str:
    """Group rows by a categorical column; counts plus numeric sums and means."""
    return _result(analysis.segment_by_column(store, dataset_name, column))


@mcp.tool()
@_guard
def find_correlations(dataset_name: str, threshold: float = 0.5) -> str:
    """Find Pearson correlations between numeric columns at/above |threshold|."""
    return _result(analysis.find_correlations(store, dataset_name, threshold))


@mcp.tool()
@_guard
def create_chart(
    dataset_name: str,
    chart_type: str,
    x: str | None = None,
    y: str | None = None,
    bins: int = 10,
) -> str:
    """Build a chart spec (bar, pie, histogram, scatter, line) from a dataset."""
    return _result(charts.build_chart(store, dataset_name, chart_type, x=x, y=y, bins=bins))


@mcp.tool()
@_guard
def run_query(
    dataset_name: str,
    filters: list[str] | None = None,
    group_by: list[str] | None = None,
    metrics: list[str] | None = None,
    sort_by: str | None = None,
    descending: bool = True,
    limit: int = 50,
) -> str:
    """Flexible query: filter/group-by/aggregate/sort/top-N.

    filters e.g. ["region==East Coast","value>100"]; metrics e.g. ["value:sum","count"].
    """
    return _result(
        query.run_query(store, dataset_name, filters, group_by, metrics, sort_by, descending, limit)
    )


@mcp.tool()
@_guard
def profile_dataset(dataset_name: str) -> str:
    """Profile data quality: nulls, duplicates, outliers, type issues, with fixes."""
    return _result(quality.profile(store, dataset_name))


@mcp.tool()
@_guard
def clean_dataset(dataset_name: str, operations: list[str]) -> str:
    """Apply cleaning ops into a new '<name>_clean' dataset (non-destructive).

    Ops: drop_duplicates, drop_nulls[:cols], fill_nulls:col:strategy,
    coerce_numeric:col, coerce_datetime:col, drop_columns:cols, drop_constant,
    drop_empty[:threshold], standardize_missing, strip_whitespace.
    """
    return _result(quality.clean(store, dataset_name, operations))


@mcp.tool()
@_guard
def run_sql(dataset_name: str, sql_query: str, limit: int = 100) -> str:
    """Run a read-only SQL SELECT/WITH query over loaded datasets (JOINs allowed).

    All loaded datasets are queryable as tables named after them. Only the named
    dataset plus any others you reference need exist. Example:
    run_sql('ecom', "SELECT region, COUNT(*) n FROM ecom GROUP BY region").
    """
    return _result(sql.run_sql(store, sql_query, limit=limit))


@mcp.tool()
@_guard
def transform_column(
    dataset_name: str,
    column: str,
    operation: str,
    params: dict | None = None,
    into: str | None = None,
) -> str:
    """Transform a column into a NEW dataset (non-destructive; default '<name>_transformed').

    operation: to_numeric|to_datetime|to_categorical|parse_json|extract_pattern|
    fill_missing|normalize|bin|map_values|split|strip|lowercase|uppercase|replace.
    Pass operation-specific options via params (e.g. {"method":"zscore"}).
    """
    return _result(transform.transform_column(store, dataset_name, column, operation, params, into))


@mcp.tool()
@_guard
def add_column(dataset_name: str, new_column: str, expression: str, into: str | None = None) -> str:
    """Add a computed column from a pandas expression into a new dataset (e.g. 'price * qty')."""
    return _result(transform.add_column(store, dataset_name, new_column, expression, into))


@mcp.tool()
@_guard
def filter_rows(
    dataset_name: str, condition: str, keep: bool = True, into: str | None = None
) -> str:
    """Materialize a row subset into a new dataset via a pandas query (e.g. 'order_value > 100')."""
    return _result(transform.filter_rows(store, dataset_name, condition, keep, into))


@mcp.tool()
@_guard
def rename_columns(dataset_name: str, mapping: dict, into: str | None = None) -> str:
    """Rename columns into a new dataset via an {old: new} mapping (non-destructive)."""
    return _result(transform.rename_columns(store, dataset_name, mapping, into))


@mcp.tool()
@_guard
def run_playbook(dataset_name: str, playbook: str) -> str:
    """Run a recipe: first_look, data_quality_audit, correlation_deep_dive, or executive_summary."""
    return _result(playbooks.run(store, playbook, dataset_name))


# =================================================================== prompts


@mcp.prompt(title="First Look Report")
def first_look_report(dataset_name: str) -> str:
    """Run the first-look playbook and return a formatted report."""
    if not store.has(dataset_name):
        return f"Dataset '{dataset_name}' is not loaded. Load it first."
    return playbooks.to_markdown(playbooks.first_look(store, dataset_name))


@mcp.prompt(title="Data Quality Audit")
def data_quality_audit(dataset_name: str) -> str:
    """Audit data quality and return issues plus a ready-to-run cleaning call."""
    if not store.has(dataset_name):
        return f"Dataset '{dataset_name}' is not loaded. Load it first."
    return playbooks.to_markdown(playbooks.data_quality_audit(store, dataset_name))


@mcp.prompt(title="List MCP Assets")
def list_mcp_assets() -> str:
    """Prime the agent with everything this server can do, plus a quick-start."""
    loaded = ", ".join(store.names()) or "(none yet)"
    return f"""# Quick Data MCP — capabilities

This server gives you arbitrary analysis over JSON/CSV datasets held in memory.

## Tools (individual actions)
- `load_dataset(file_path, dataset_name)` — load a .json/.csv file
- `list_datasets()` — what is loaded right now
- `dataset_breakdown(dataset_name)` — shape, column types, null counts, sample
- `suggest_analysis(dataset_name)` — schema-driven next-step ideas
- `segment_by_column(dataset_name, column)` — group + aggregate by a category
- `find_correlations(dataset_name, threshold=0.5)` — numeric relationships
- `create_chart(dataset_name, chart_type, x, y)` — bar/pie/histogram/scatter/line
- `run_query(dataset_name, filters, group_by, metrics, ...)` — flexible query
- `run_sql(dataset_name, sql_query)` — read-only SQL over loaded datasets (JOINs allowed)
- `profile_dataset(dataset_name)` — data-quality profile + suggested fixes
- `clean_dataset(dataset_name, operations)` — apply fixes into a new dataset
- `transform_column(dataset_name, column, operation, params)` — non-destructive column transform
- `add_column(dataset_name, new_column, expression)` — computed column into a new dataset
- `filter_rows(dataset_name, condition, keep)` — materialize a row subset
- `rename_columns(dataset_name, mapping)` — rename into a new dataset
- `run_playbook(dataset_name, playbook)` — first_look / data_quality_audit / correlation_deep_dive / executive_summary

## Prompts (guided workflows — these slash commands)
- `find_data_sources(directory)` — discover loadable files, ready to load
- `dataset_first_look(dataset_name)` — orient yourself on a fresh dataset
- `correlation_investigation(dataset_name)` — hunt for strong relationships
- `trend_analysis(dataset_name, date_column?, metric?)` — time-series direction + change
- `first_look_report(dataset_name)` — formatted first-look report
- `data_quality_audit(dataset_name)` — quality issues + ready cleaning call
- `executive_summary(dataset_name)` — C-suite report: takeaways, trend, relationships

## Quick start
1. `find_data_sources(".")` to discover files (or sample data in `{DATA_DIR}`)
2. `load_dataset(<path>, <name>)`
3. `dataset_first_look(<name>)`, then `correlation_investigation(<name>)`

Currently loaded: {loaded}
"""


@mcp.prompt(title="Find Data Sources")
def find_data_sources(directory: str = ".") -> str:
    """Discover loadable .json/.csv files in a directory, with load commands."""
    base = Path(directory)
    search_dirs = [base]
    if base.resolve() != DATA_DIR and DATA_DIR.exists():
        search_dirs.append(DATA_DIR)

    found: list[Path] = []
    for d in search_dirs:
        if d.exists():
            for ext in ("*.json", "*.csv", "*.tsv"):
                found.extend(sorted(d.glob(ext)))

    if not found:
        return (
            f"No .json/.csv/.tsv files found under '{directory}'"
            + (f" or the bundled data dir '{DATA_DIR}'." if DATA_DIR.exists() else ".")
            + "\nDrop a dataset somewhere and try again."
        )

    lines = ["# Data sources found", "", "Ready to load:"]
    for p in found:
        suggested = p.stem.replace("-", "_").replace(" ", "_")
        lines.append(f"- `load_dataset(\"{p.as_posix()}\", \"{suggested}\")`")
    lines += ["", "After loading, run `dataset_first_look(<name>)` to orient yourself."]
    return "\n".join(lines)


@mcp.prompt(title="Dataset First Look")
def dataset_first_look(dataset_name: str) -> str:
    """Orient the agent on a freshly loaded dataset and propose next steps."""
    if not store.has(dataset_name):
        return (
            f"Dataset '{dataset_name}' is not loaded. Run `list_datasets()` to see "
            f"what's available, or `load_dataset(<path>, '{dataset_name}')` first."
        )
    b = analysis.breakdown(store, dataset_name)
    numeric = ", ".join(b["numerical_columns"]) or "none"
    categorical = ", ".join(b["categorical_columns"]) or "none"
    # Use the schema-aware suggestions so we skip identifier-like columns.
    segment_cols = [
        s["column"]
        for s in analysis.suggest_analysis(store, dataset_name)["suggestions"]
        if s["operation"] == "segment"
    ]
    steps = []
    if segment_cols:
        steps.append(
            f"- Segment: `segment_by_column('{dataset_name}', '{segment_cols[0]}')`"
        )
    if len(b["numerical_columns"]) >= 2:
        steps.append(f"- Correlations: `correlation_investigation('{dataset_name}')`")
    if b["numerical_columns"]:
        steps.append(
            f"- Distribution: `create_chart('{dataset_name}', 'histogram', "
            f"x='{b['numerical_columns'][0]}')`"
        )

    return f"""# First look — `{dataset_name}`

- Rows: {b['rows']}
- Numerical columns: {numeric}
- Categorical columns: {categorical}

Call `dataset_breakdown('{dataset_name}')` for the full schema and a sample.

## Suggested next steps
{chr(10).join(steps) or '- No obvious next steps; inspect the breakdown.'}
"""


@mcp.prompt(title="Correlation Investigation")
def correlation_investigation(dataset_name: str, threshold: float = 0.5) -> str:
    """Run a correlation scan and report the strongest relationships found."""
    if not store.has(dataset_name):
        return (
            f"Dataset '{dataset_name}' is not loaded. Load it first with "
            f"`load_dataset(<path>, '{dataset_name}')`."
        )
    try:
        result = analysis.find_correlations(store, dataset_name, threshold)
    except DatasetError as exc:
        return f"Cannot run correlation analysis: {exc}"

    pairs = result["correlations"]
    if not pairs:
        return (
            f"No correlations with |r| ≥ {threshold} in '{dataset_name}'. "
            f"Try a lower threshold, e.g. `correlation_investigation('{dataset_name}', 0.3)`."
        )

    lines = [f"# Correlations in `{dataset_name}` (|r| ≥ {threshold})", ""]
    for p in pairs:
        lines.append(
            f"- **{p['x']} ↔ {p['y']}**: r = {p['r']} ({p['strength']}, {p['direction']})"
        )
    top = pairs[0]
    lines += [
        "",
        f"Strongest: **{top['x']} ↔ {top['y']}** (r = {top['r']}). Visualize it with "
        f"`create_chart('{dataset_name}', 'scatter', x='{top['x']}', y='{top['y']}')`.",
    ]
    return "\n".join(lines)


@mcp.prompt(title="Trend Analysis")
def trend_analysis(dataset_name: str, date_column: str = "", metric: str = "") -> str:
    """Detect a metric's time-series trend and report direction and change."""
    if not store.has(dataset_name):
        return f"Dataset '{dataset_name}' is not loaded. Load it first."
    try:
        t = analysis.trend_analysis(
            store,
            dataset_name,
            date_column=date_column or None,
            metric=metric or None,
        )
    except DatasetError as exc:
        return f"Cannot run trend analysis: {exc}"

    arrow = {"rising": "↑", "falling": "↓", "flat": "→"}[t["direction"]]
    pct = f"{t['change_pct']:+.1f}%" if t["change_pct"] is not None else "n/a"
    lines = [
        f"# Trend — `{dataset_name}`",
        "",
        f"**{t['metric']}** by `{t['date_column']}`, {t['frequency']} buckets "
        f"({t['periods']} periods).",
        "",
        f"- Direction: **{t['direction']}** {arrow} ({pct} first→last)",
        f"- First: {t['first']}  →  Last: {t['last']}",
        f"- Peak: {t['peak']['value']} on {t['peak']['period']}",
        f"- Low: {t['trough']['value']} on {t['trough']['period']}",
        "",
        f"Run `executive_summary('{dataset_name}')` for the full picture, or "
        f"`run_playbook('{dataset_name}', 'correlation_deep_dive')` to find drivers.",
    ]
    return "\n".join(lines)


@mcp.prompt(title="Executive Summary")
def executive_summary(dataset_name: str) -> str:
    """C-suite summary: takeaways, key breakdown, trend, relationships, confidence."""
    if not store.has(dataset_name):
        return f"Dataset '{dataset_name}' is not loaded. Load it first."
    return playbooks.to_markdown(playbooks.executive_summary(store, dataset_name))


def main() -> None:
    """Console entry point. Runs over stdio for MCP clients like Claude Code."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
