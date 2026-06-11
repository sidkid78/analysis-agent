"""Flexible querying over a dataset.

A small, model-friendly string DSL so an LLM can express arbitrary
filter / group-by / aggregate / sort / top-N queries without arbitrary code:

- filters:  ["region==East Coast", "order_value>100", "name~smith"]
- group_by: ["region", "product_category"]
- metrics:  ["order_value:sum", "order_value:mean", "count"]
- sort_by:  a column present in the result; descending toggles direction
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .analysis import _json_safe
from .store import DatasetError, DatasetStore

# Longest operators first so ">=" isn't parsed as ">".
_OPS = ["<=", ">=", "!=", "==", "~", ">", "<"]
_FILTER_RE = re.compile(r"^\s*(.+?)\s*(" + "|".join(map(re.escape, _OPS)) + r")\s*(.*?)\s*$")

_AGGS = {
    "count": "count",
    "sum": "sum",
    "mean": "mean",
    "avg": "mean",
    "min": "min",
    "max": "max",
    "median": "median",
    "std": "std",
    "nunique": "nunique",
}


def _coerce(value: str) -> Any:
    v = value.strip().strip("'\"")
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _apply_filter(df: pd.DataFrame, expr: str) -> pd.DataFrame:
    m = _FILTER_RE.match(expr)
    if not m:
        raise DatasetError(f"Cannot parse filter '{expr}'. Use e.g. 'region==East Coast'.")
    col, op, raw = m.group(1), m.group(2), m.group(3)
    if col not in df.columns:
        raise DatasetError(f"Filter column '{col}' not found. Columns: {', '.join(map(str, df.columns))}.")
    val = _coerce(raw)
    series = df[col]
    if op == "==":
        return df[series == val]
    if op == "!=":
        return df[series != val]
    if op == "~":
        return df[series.astype(str).str.contains(str(val), case=False, na=False)]
    # Ordered comparisons: coerce to numeric where possible.
    numeric = pd.to_numeric(series, errors="coerce")
    if op == ">":
        return df[numeric > val]
    if op == ">=":
        return df[numeric >= val]
    if op == "<":
        return df[numeric < val]
    if op == "<=":
        return df[numeric <= val]
    raise DatasetError(f"Unsupported operator '{op}'.")


def _parse_metric(spec: str) -> tuple[str | None, str]:
    spec = spec.strip()
    if spec.lower() == "count":
        return None, "count"
    if ":" not in spec:
        raise DatasetError(f"Metric '{spec}' must be 'column:agg' or 'count'.")
    col, agg = spec.rsplit(":", 1)
    agg = agg.strip().lower()
    if agg not in _AGGS:
        raise DatasetError(f"Unknown aggregation '{agg}'. Use one of: {', '.join(sorted(_AGGS))}.")
    return col.strip(), agg


def run_query(
    store: DatasetStore,
    name: str,
    filters: list[str] | None = None,
    group_by: list[str] | None = None,
    metrics: list[str] | None = None,
    sort_by: str | None = None,
    descending: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    df = store.frame(name)
    filters = filters or []
    group_by = [g for g in (group_by or []) if g]
    metrics = [m for m in (metrics or []) if m]

    for expr in filters:
        df = _apply_filter(df, expr)

    for g in group_by:
        if g not in df.columns:
            raise DatasetError(f"group_by column '{g}' not found. Columns: {', '.join(map(str, df.columns))}.")

    matched = int(len(df))

    if group_by:
        grouped = df.groupby(group_by, dropna=False)
        if metrics:
            out_cols: dict[str, pd.Series] = {}
            for spec in metrics:
                col, agg = _parse_metric(spec)
                if col is None:
                    out_cols["count"] = grouped.size()
                else:
                    if col not in df.columns:
                        raise DatasetError(f"Metric column '{col}' not found.")
                    out_cols[f"{col}_{agg}"] = grouped[col].agg(agg)
            result = pd.DataFrame(out_cols).reset_index()
        else:
            result = grouped.size().reset_index(name="count")
    elif metrics:
        row: dict[str, Any] = {}
        for spec in metrics:
            col, agg = _parse_metric(spec)
            if col is None:
                row["count"] = len(df)
            else:
                if col not in df.columns:
                    raise DatasetError(f"Metric column '{col}' not found.")
                row[f"{col}_{agg}"] = getattr(df[col], agg)()
        result = pd.DataFrame([row])
    else:
        result = df

    if sort_by:
        if sort_by not in result.columns:
            raise DatasetError(
                f"sort_by '{sort_by}' not in result columns: {', '.join(map(str, result.columns))}."
            )
        result = result.sort_values(sort_by, ascending=not descending)
    elif group_by or metrics:
        # Default: sort grouped output by its last metric column, descending.
        last = [c for c in result.columns if c not in group_by]
        if last:
            result = result.sort_values(last[-1], ascending=False)

    total_rows = int(len(result))
    result = result.head(max(1, int(limit)))
    rows = [
        {k: _json_safe(v) for k, v in rec.items()}
        for rec in result.to_dict(orient="records")
    ]
    return {
        "dataset": name,
        "matched_rows": matched,
        "result_rows": total_rows,
        "returned_rows": len(rows),
        "columns": [str(c) for c in result.columns],
        "rows": rows,
    }
