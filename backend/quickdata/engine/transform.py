"""Column- and row-level dataset transforms.

Like :mod:`quickdata.engine.quality`'s ``clean``, every transform here is
**non-destructive**: it reads the source dataset and writes the result into a
*new* dataset (``into`` or ``<name>_transformed`` by default), leaving the
original untouched. Computed columns use ``df.eval`` and row filters use
``df.query`` — pandas-native expressions, never bare ``eval``.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .analysis import _json_safe
from .store import DatasetError, DatasetStore

_COLUMN_OPS = (
    "to_numeric", "to_datetime", "to_categorical", "parse_json", "extract_pattern",
    "fill_missing", "normalize", "bin", "map_values", "split", "strip",
    "lowercase", "uppercase", "replace",
)


def _require_col(df: pd.DataFrame, col: str) -> None:
    if col not in df.columns:
        raise DatasetError(
            f"Column '{col}' not found. Columns: {', '.join(map(str, df.columns))}."
        )


def _sample(series: pd.Series, n: int = 3) -> list[Any]:
    return [_json_safe(v) for v in series.dropna().head(n).tolist()]


def _store_result(
    store: DatasetStore, source: str, df: pd.DataFrame, into: str | None
) -> tuple[str, Any]:
    target = into or f"{source}_transformed"
    info = store.load_dataframe(target, df, source=f"transformed from '{source}'")
    return target, info.to_dict()


def transform_column(
    store: DatasetStore,
    name: str,
    column: str,
    operation: str,
    params: dict[str, Any] | None = None,
    into: str | None = None,
) -> dict[str, Any]:
    """Apply a single-column transformation into a new dataset.

    Operations (params in parentheses):
      - to_numeric / to_datetime (format) / to_categorical: change dtype
      - parse_json (expand): parse JSON strings; expand=True spreads keys to columns
      - extract_pattern (pattern): regex capture into the column
      - fill_missing (method=value|ffill|bfill|mean|median|mode, value): fill nulls
      - normalize (method=minmax|zscore|robust): rescale a numeric column
      - bin (bins, labels, new_column): bucket a numeric column into a new column
      - map_values (mapping, default): remap values via a dict
      - split (delimiter, max_splits, prefix): split a string column into columns
      - strip / lowercase / uppercase: string cleanup
      - replace (old, new, regex): string replacement
    """
    params = params or {}
    df = store.frame(name).copy()
    _require_col(df, column)
    if operation not in _COLUMN_OPS:
        raise DatasetError(
            f"Unknown operation '{operation}'. Options: {', '.join(_COLUMN_OPS)}."
        )

    before = {
        "dtype": str(df[column].dtype),
        "null_count": int(df[column].isna().sum()),
        "sample": _sample(df[column]),
    }
    new_columns: list[str] = []
    details: dict[str, Any] = {}

    if operation == "to_numeric":
        df[column] = pd.to_numeric(df[column], errors=params.get("errors", "coerce"))

    elif operation == "to_datetime":
        fmt = params.get("format")
        df[column] = pd.to_datetime(
            df[column], format=fmt, errors=params.get("errors", "coerce")
        )

    elif operation == "to_categorical":
        df[column] = df[column].astype("category")
        details["category_count"] = int(len(df[column].cat.categories))

    elif operation == "parse_json":
        def _parse(val: Any) -> Any:
            if pd.isna(val):
                return None
            try:
                return json.loads(str(val))
            except (json.JSONDecodeError, TypeError):
                return None

        parsed = df[column].apply(_parse)
        if params.get("expand", False):
            keys: set[str] = set()
            for item in parsed.dropna():
                if isinstance(item, dict):
                    keys.update(item.keys())
            for key in sorted(keys):
                new_col = f"{column}_{key}"
                df[new_col] = parsed.apply(
                    lambda x, k=key: x.get(k) if isinstance(x, dict) else None
                )
                new_columns.append(new_col)
            details["keys_found"] = sorted(keys)
        else:
            df[column] = parsed

    elif operation == "extract_pattern":
        pattern = params.get("pattern")
        if not pattern:
            raise DatasetError("extract_pattern requires a 'pattern' param.")
        df[column] = df[column].astype(str).str.extract(pattern, expand=False)
        details["pattern"] = pattern

    elif operation == "fill_missing":
        method = params.get("method", "value")
        if method == "value":
            df[column] = df[column].fillna(params.get("value", ""))
        elif method == "ffill":
            df[column] = df[column].ffill()
        elif method == "bfill":
            df[column] = df[column].bfill()
        elif method in ("mean", "median"):
            if not pd.api.types.is_numeric_dtype(df[column]):
                raise DatasetError(f"'{method}' fill needs a numeric column.")
            df[column] = df[column].fillna(getattr(df[column], method)())
        elif method == "mode":
            mode = df[column].mode(dropna=True)
            if not mode.empty:
                df[column] = df[column].fillna(mode.iloc[0])
        else:
            raise DatasetError(f"Unknown fill method '{method}'.")
        details["method"] = method

    elif operation == "normalize":
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise DatasetError("normalize needs a numeric column.")
        method = params.get("method", "minmax")
        s = df[column]
        if method == "minmax":
            lo, hi = s.min(), s.max()
            if hi == lo:
                raise DatasetError(f"Cannot minmax-normalize constant column '{column}'.")
            df[column] = (s - lo) / (hi - lo)
        elif method == "zscore":
            std = s.std()
            if not std:
                raise DatasetError(f"Cannot zscore-normalize zero-variance column '{column}'.")
            df[column] = (s - s.mean()) / std
        elif method == "robust":
            iqr = s.quantile(0.75) - s.quantile(0.25)
            if not iqr:
                raise DatasetError(f"Cannot robust-normalize column '{column}' (IQR is 0).")
            df[column] = (s - s.median()) / iqr
        else:
            raise DatasetError(f"Unknown normalize method '{method}'.")
        details["method"] = method

    elif operation == "bin":
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise DatasetError("bin needs a numeric column.")
        new_col = params.get("new_column", f"{column}_binned")
        binned = pd.cut(df[column], bins=params.get("bins", 5), labels=params.get("labels"))
        df[new_col] = binned.astype(str)
        new_columns.append(new_col)

    elif operation == "map_values":
        mapping = params.get("mapping") or {}
        if not mapping:
            raise DatasetError("map_values requires a non-empty 'mapping' param.")
        mapped = df[column].map(mapping)
        if "default" in params and params["default"] is not None:
            mapped = mapped.fillna(params["default"])
        df[column] = mapped

    elif operation == "split":
        delimiter = params.get("delimiter", ",")
        max_splits = params.get("max_splits", -1)
        prefix = params.get("prefix", column)
        parts = df[column].astype(str).str.split(
            delimiter, n=max_splits if max_splits and max_splits > 0 else -1, expand=True
        )
        for i in range(parts.shape[1]):
            new_col = f"{prefix}_{i + 1}"
            df[new_col] = parts[i]
            new_columns.append(new_col)

    elif operation == "strip":
        df[column] = df[column].astype(str).str.strip()
        df.loc[df[column] == "nan", column] = np.nan

    elif operation == "lowercase":
        df[column] = df[column].astype(str).str.lower()

    elif operation == "uppercase":
        df[column] = df[column].astype(str).str.upper()

    elif operation == "replace":
        old = params.get("old")
        if old is None:
            raise DatasetError("replace requires an 'old' param.")
        df[column] = df[column].astype(str).str.replace(
            old, params.get("new", ""), regex=bool(params.get("regex", False))
        )

    target, result = _store_result(store, name, df, into)
    after = {
        "dtype": str(df[column].dtype),
        "null_count": int(df[column].isna().sum()),
        "sample": _sample(df[column]),
    }
    return {
        "source": name,
        "transformed_dataset": target,
        "column": column,
        "operation": operation,
        "details": details,
        "new_columns": new_columns,
        "before": before,
        "after": after,
        "result": result,
    }


def add_column(
    store: DatasetStore,
    name: str,
    new_column: str,
    expression: str,
    into: str | None = None,
) -> dict[str, Any]:
    """Add a computed column from a pandas ``df.eval`` expression (e.g. 'price * qty')."""
    df = store.frame(name).copy()
    try:
        df[new_column] = df.eval(expression)
    except Exception as exc:
        raise DatasetError(
            f"Could not evaluate expression '{expression}': {exc}. "
            f"Use column names directly, e.g. 'revenue - cost'."
        ) from exc
    target, result = _store_result(store, name, df, into)
    return {
        "source": name,
        "transformed_dataset": target,
        "new_column": new_column,
        "expression": expression,
        "dtype": str(df[new_column].dtype),
        "sample": _sample(df[new_column], 5),
        "result": result,
    }


def filter_rows(
    store: DatasetStore,
    name: str,
    condition: str,
    keep: bool = True,
    into: str | None = None,
) -> dict[str, Any]:
    """Materialize a row subset into a new dataset using a ``df.query`` condition.

    With keep=True, rows matching ``condition`` are kept; with keep=False they are
    dropped. Example conditions: "order_value > 100", "region == 'East Coast'".
    """
    df = store.frame(name)
    before = int(len(df))
    try:
        matched = df.query(condition)
    except Exception as exc:
        raise DatasetError(
            f"Invalid filter condition '{condition}': {exc}. "
            f"Use pandas query syntax, e.g. \"region == 'East Coast'\"."
        ) from exc
    result_df = matched if keep else df.drop(matched.index)
    target, result = _store_result(store, name, result_df.copy(), into)
    return {
        "source": name,
        "transformed_dataset": target,
        "condition": condition,
        "keep_matching": keep,
        "rows_before": before,
        "rows_after": int(len(result_df)),
        "result": result,
    }


def rename_columns(
    store: DatasetStore,
    name: str,
    mapping: dict[str, str],
    into: str | None = None,
) -> dict[str, Any]:
    """Rename columns into a new dataset via an {old: new} mapping."""
    df = store.frame(name)
    missing = [c for c in mapping if c not in df.columns]
    if missing:
        raise DatasetError(
            f"Columns not found: {', '.join(missing)}. "
            f"Columns: {', '.join(map(str, df.columns))}."
        )
    renamed = df.rename(columns=mapping)
    target, result = _store_result(store, name, renamed.copy(), into)
    return {
        "source": name,
        "transformed_dataset": target,
        "renamed": mapping,
        "columns": [str(c) for c in renamed.columns],
        "result": result,
    }
