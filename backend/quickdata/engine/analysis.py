"""Analysis operations over stored datasets.

Each function takes a :class:`DatasetStore` and a dataset name and returns plain
JSON-serializable dicts, so the same return value works for both an MCP tool
result and an HTTP response body.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from .store import DatasetError, DatasetStore


def _json_safe(value: Any) -> Any:
    """Coerce numpy/pandas scalars and NaN/inf into JSON-friendly values."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def breakdown(store: DatasetStore, name: str, sample_rows: int = 5) -> dict[str, Any]:
    """Shape, per-column schema/null stats, and a few sample rows."""
    df = store.frame(name)
    info = store.info(name)
    sample = df.head(sample_rows).to_dict(orient="records")
    sample = [{k: _json_safe(v) for k, v in row.items()} for row in sample]
    return {
        "dataset": name,
        "rows": info.rows,
        "columns": [c.to_dict() for c in info.columns],
        "numerical_columns": info.columns_of_kind("numerical"),
        "categorical_columns": info.columns_of_kind("categorical", "boolean"),
        "datetime_columns": info.columns_of_kind("datetime"),
        "sample": sample,
    }


def suggest_analysis(store: DatasetStore, name: str) -> dict[str, Any]:
    """Heuristic next-step suggestions based on the dataset's schema."""
    info = store.info(name)
    numeric = info.columns_of_kind("numerical")
    categorical = info.columns_of_kind("categorical", "boolean")
    suggestions: list[dict[str, str]] = []

    # Skip identifier-like columns (nearly unique) — segmenting by them is noise.
    rows = max(info.rows, 1)
    by_name = {c.name: c for c in info.columns}
    segmentable = [
        col
        for col in categorical
        if by_name[col].unique_count <= max(2, min(50, int(rows * 0.5)))
    ]

    for col in segmentable[:3]:
        suggestions.append(
            {
                "title": f"Segment by '{col}'",
                "operation": "segment",
                "column": col,
                "why": f"'{col}' is categorical — group rows to compare counts and "
                f"numeric totals across its values.",
            }
        )
    if len(numeric) >= 2:
        suggestions.append(
            {
                "title": "Find correlations",
                "operation": "correlations",
                "why": f"{len(numeric)} numeric columns present — look for strong "
                "relationships between them.",
            }
        )
    for col in numeric[:2]:
        suggestions.append(
            {
                "title": f"Distribution of '{col}'",
                "operation": "chart",
                "column": col,
                "why": f"'{col}' is numeric — a histogram reveals its distribution.",
            }
        )
    return {
        "dataset": name,
        "numerical_columns": numeric,
        "categorical_columns": categorical,
        "suggestions": suggestions,
    }


def segment_by_column(
    store: DatasetStore, name: str, column: str, top: int = 20
) -> dict[str, Any]:
    """Group by a categorical column; counts + sums/means of numeric columns."""
    df = store.frame(name)
    if column not in df.columns:
        raise DatasetError(
            f"Column '{column}' not in '{name}'. Columns: {', '.join(map(str, df.columns))}."
        )

    info = store.info(name)
    numeric_cols = info.columns_of_kind("numerical")
    grouped = df.groupby(column, dropna=False)

    segments: list[dict[str, Any]] = []
    counts = grouped.size().sort_values(ascending=False)
    for value, count in counts.head(top).items():
        seg: dict[str, Any] = {"value": _json_safe(value), "count": int(count)}
        for ncol in numeric_cols:
            series = grouped.get_group(value)[ncol]
            seg[f"{ncol}_sum"] = _json_safe(series.sum())
            seg[f"{ncol}_mean"] = _json_safe(series.mean())
        segments.append(seg)

    return {
        "dataset": name,
        "column": column,
        "distinct_values": int(counts.size),
        "numeric_aggregates": numeric_cols,
        "segments": segments,
    }


def find_correlations(
    store: DatasetStore, name: str, threshold: float = 0.5
) -> dict[str, Any]:
    """Pearson correlations between numeric column pairs at/above |threshold|."""
    df = store.frame(name)
    info = store.info(name)
    numeric_cols = info.columns_of_kind("numerical")
    if len(numeric_cols) < 2:
        raise DatasetError(
            f"Need at least two numerical columns for correlation analysis; "
            f"'{name}' has {len(numeric_cols)} ({', '.join(numeric_cols) or 'none'})."
        )

    corr = df[numeric_cols].corr(numeric_only=True)
    pairs: list[dict[str, Any]] = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            r = corr.loc[a, b]
            if pd.isna(r):
                continue
            if abs(r) >= threshold:
                pairs.append(
                    {
                        "x": a,
                        "y": b,
                        "r": round(float(r), 4),
                        "strength": _strength(abs(float(r))),
                        "direction": "positive" if r >= 0 else "negative",
                    }
                )
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    return {
        "dataset": name,
        "threshold": threshold,
        "numerical_columns": numeric_cols,
        "correlations": pairs,
    }


def _strength(abs_r: float) -> str:
    if abs_r >= 0.8:
        return "very strong"
    if abs_r >= 0.6:
        return "strong"
    if abs_r >= 0.4:
        return "moderate"
    return "weak"


# Column names that hint at a date/time, used when no column is typed datetime.
_DATE_NAME_HINT = re.compile(r"(date|time|day|month|year|timestamp|_at|_on)", re.I)


def _pick_date_column(df: pd.DataFrame, info: Any) -> str | None:
    """Best-effort date column: prefer a datetime-typed one, else a parseable
    date-like-named string column (CSV dates often arrive as plain strings)."""
    dt_cols = info.columns_of_kind("datetime")
    if dt_cols:
        return dt_cols[0]
    for col in info.columns_of_kind("categorical"):
        if not _DATE_NAME_HINT.search(str(col)):
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().mean() >= 0.8:
            return col
    return None


def _auto_freq(index: pd.DatetimeIndex) -> str:
    """Pick a resample rule from the time span so we get a readable number of
    buckets. Uses pandas 2.2+ aliases (ME/YE)."""
    span_days = int((index.max() - index.min()).days)
    if span_days <= 31:
        return "D"
    if span_days <= 186:
        return "W"
    if span_days <= 1100:
        return "ME"
    return "YE"


def trend_analysis(
    store: DatasetStore,
    name: str,
    date_column: str | None = None,
    metric: str | None = None,
    freq: str = "auto",
) -> dict[str, Any]:
    """Aggregate a numeric metric over time and characterize the trend.

    The date column and metric are auto-detected when not given. Date-like string
    columns are coerced to datetime. With no usable numeric metric, the row count
    per period is used. Returns the per-period series, a direction/percent-change
    summary, and a ready-to-render chart spec.
    """
    df = store.frame(name)
    info = store.info(name)

    date_column = date_column or _pick_date_column(df, info)
    if not date_column:
        raise DatasetError(
            f"No datetime column found in '{name}'. Pass date_column=<column> with "
            f"parseable dates."
        )
    if date_column not in df.columns:
        raise DatasetError(
            f"Column '{date_column}' not in '{name}'. Columns: "
            f"{', '.join(map(str, df.columns))}."
        )
    dates = pd.to_datetime(df[date_column], errors="coerce")
    if int(dates.notna().sum()) < 2:
        raise DatasetError(
            f"Column '{date_column}' has fewer than 2 parseable dates; cannot "
            f"analyze a trend."
        )

    numeric_cols = info.columns_of_kind("numerical")
    if metric is not None and metric not in df.columns:
        raise DatasetError(f"Metric '{metric}' not in '{name}'.")
    if metric is not None and metric not in numeric_cols:
        raise DatasetError(
            f"Metric '{metric}' is not numeric. Numeric columns: "
            f"{', '.join(numeric_cols) or 'none'}."
        )
    if metric is None:
        metric = next((c for c in numeric_cols if c != date_column), None)

    ts = pd.DataFrame({"_t": dates})
    if metric is None:
        ts["_v"] = 1.0
        metric_label = "row count"
    else:
        ts["_v"] = pd.to_numeric(df[metric], errors="coerce")
        metric_label = f"sum({metric})"
    ts = ts.dropna(subset=["_t"]).set_index("_t").sort_index()

    rule = _auto_freq(ts.index) if freq == "auto" else freq
    resampled = ts["_v"].resample(rule)
    grouped = (resampled.count() if metric is None else resampled.sum()).dropna()
    if grouped.empty:
        raise DatasetError("No data points after resampling; check the metric column.")

    points = [
        {"period": idx.date().isoformat(), "value": _json_safe(val)}
        for idx, val in grouped.items()
    ]
    values = [p["value"] for p in points]
    first, last = values[0], values[-1]
    change = last - first
    change_pct = round((change / first) * 100, 2) if first else None
    slope = float(np.polyfit(range(len(values)), values, 1)[0]) if len(values) >= 2 else 0.0
    direction = "rising" if slope > 0 else "falling" if slope < 0 else "flat"
    peak = max(points, key=lambda p: p["value"])
    trough = min(points, key=lambda p: p["value"])

    chart = {
        "dataset": name,
        "type": "bar",
        "subtype": "trend",
        "title": f"{metric_label} over time ({rule})",
        "x_label": date_column,
        "y_label": metric_label,
        "data": [{"label": p["period"], "value": p["value"]} for p in points],
    }

    return {
        "dataset": name,
        "date_column": date_column,
        "metric": metric_label,
        "frequency": rule,
        "periods": len(points),
        "series": points,
        "first": _json_safe(first),
        "last": _json_safe(last),
        "change": _json_safe(change),
        "change_pct": change_pct,
        "direction": direction,
        "slope": round(slope, 4),
        "peak": peak,
        "trough": trough,
        "chart": chart,
    }
