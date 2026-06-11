"""Data-quality profiling and cleaning.

``profile`` reports per-column issues and dataset-level problems with suggested
fixes. ``clean`` applies a list of cleaning operations into a *new* dataset
(non-destructive) using a small string DSL:

- "drop_duplicates"
- "drop_nulls"                     (drop rows with any null)
- "drop_nulls:colA,colB"          (drop rows null in those columns)
- "fill_nulls:col:median"         (strategy: mean|median|mode|zero|<literal>)
- "coerce_numeric:col"
- "coerce_datetime:col"
- "drop_columns:colA,colB"
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .analysis import _json_safe
from .store import DatasetError, DatasetStore


def profile(store: DatasetStore, name: str) -> dict[str, Any]:
    df = store.frame(name)
    rows = len(df)
    columns: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    dup_count = int(df.duplicated().sum())
    if dup_count:
        issues.append(
            {
                "severity": "warning",
                "issue": f"{dup_count} duplicate row(s)",
                "fix": "drop_duplicates",
            }
        )

    for col in df.columns:
        s = df[col]
        nulls = int(s.isna().sum())
        null_pct = round(100 * nulls / rows, 1) if rows else 0.0
        unique = int(s.nunique(dropna=True))
        is_numeric = pd.api.types.is_numeric_dtype(s)
        info: dict[str, Any] = {
            "name": str(col),
            "dtype": str(s.dtype),
            "null_count": nulls,
            "null_pct": null_pct,
            "unique_count": unique,
        }

        if rows and unique <= 1:
            issues.append(
                {"severity": "info", "issue": f"'{col}' is constant", "fix": f"drop_columns:{col}"}
            )
        if null_pct >= 40:
            issues.append(
                {
                    "severity": "warning",
                    "issue": f"'{col}' is {null_pct}% null",
                    "fix": f"fill_nulls:{col}:median" if is_numeric else f"drop_columns:{col}",
                }
            )
        if rows and unique == rows and not is_numeric:
            info["note"] = "identifier-like (all values unique)"

        # Object column that is mostly numeric → suggest coercion.
        if not is_numeric and s.dtype == object:
            coerced = pd.to_numeric(s, errors="coerce")
            good = coerced.notna().sum()
            non_null = s.notna().sum()
            if non_null and good / non_null >= 0.9 and good > 0:
                issues.append(
                    {
                        "severity": "info",
                        "issue": f"'{col}' looks numeric but is stored as text",
                        "fix": f"coerce_numeric:{col}",
                    }
                )

        if is_numeric and s.notna().sum() >= 8:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if iqr and not np.isnan(iqr):
                lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                outliers = int(((s < lo) | (s > hi)).sum())
                if outliers:
                    info["outliers"] = outliers
                    info["outlier_bounds"] = [_json_safe(lo), _json_safe(hi)]

        columns.append(info)

    score = _quality_score(rows, len(df.columns), issues)
    return {
        "dataset": name,
        "rows": rows,
        "duplicate_rows": dup_count,
        "columns": columns,
        "issues": issues,
        "quality_score": score,
    }


def _quality_score(rows: int, ncols: int, issues: list[dict[str, str]]) -> int:
    penalty = sum(8 if i["severity"] == "warning" else 3 for i in issues)
    return max(0, 100 - penalty)


def clean(store: DatasetStore, name: str, operations: list[str], into: str | None = None) -> dict[str, Any]:
    df = store.frame(name).copy()
    target = into or f"{name}_clean"
    log: list[str] = []
    before = len(df)

    for op in operations:
        op = op.strip()
        if not op:
            continue
        head, _, arg = op.partition(":")
        head = head.strip().lower()

        if head == "drop_duplicates":
            n = len(df)
            df = df.drop_duplicates()
            log.append(f"drop_duplicates: removed {n - len(df)} row(s)")
        elif head == "drop_nulls":
            cols = [c.strip() for c in arg.split(",") if c.strip()] or None
            n = len(df)
            df = df.dropna(subset=cols)
            log.append(f"drop_nulls{f' ({arg})' if arg else ''}: removed {n - len(df)} row(s)")
        elif head == "fill_nulls":
            col, _, strat = arg.partition(":")
            col, strat = col.strip(), (strat.strip() or "zero")
            _require_col(df, col)
            df[col] = _fill(df[col], strat)
            log.append(f"fill_nulls: '{col}' with {strat}")
        elif head == "coerce_numeric":
            col = arg.strip()
            _require_col(df, col)
            df[col] = pd.to_numeric(df[col], errors="coerce")
            log.append(f"coerce_numeric: '{col}'")
        elif head == "coerce_datetime":
            col = arg.strip()
            _require_col(df, col)
            df[col] = pd.to_datetime(df[col], errors="coerce")
            log.append(f"coerce_datetime: '{col}'")
        elif head == "drop_columns":
            cols = [c.strip() for c in arg.split(",") if c.strip()]
            for c in cols:
                _require_col(df, c)
            df = df.drop(columns=cols)
            log.append(f"drop_columns: {', '.join(cols)}")
        else:
            raise DatasetError(f"Unknown cleaning operation '{op}'.")

    info = store.load_dataframe(target, df, source=f"cleaned from '{name}'")
    return {
        "source": name,
        "cleaned_dataset": target,
        "rows_before": before,
        "rows_after": len(df),
        "operations": log,
        "result": info.to_dict(),
    }


def _require_col(df: pd.DataFrame, col: str) -> None:
    if col not in df.columns:
        raise DatasetError(f"Column '{col}' not found. Columns: {', '.join(map(str, df.columns))}.")


def _fill(series: pd.Series, strategy: str) -> pd.Series:
    s = strategy.lower()
    if s == "mean":
        return series.fillna(pd.to_numeric(series, errors="coerce").mean())
    if s == "median":
        return series.fillna(pd.to_numeric(series, errors="coerce").median())
    if s == "mode":
        mode = series.mode(dropna=True)
        return series.fillna(mode.iloc[0]) if not mode.empty else series
    if s == "zero":
        return series.fillna(0)
    # Literal fill value.
    return series.fillna(strategy)
