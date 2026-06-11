"""Analysis operations over stored datasets.

Each function takes a :class:`DatasetStore` and a dataset name and returns plain
JSON-serializable dicts, so the same return value works for both an MCP tool
result and an HTTP response body.
"""

from __future__ import annotations

import math
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
