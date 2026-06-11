"""Chart spec builders.

These return transport-neutral chart *specs* (type + data + labels) rather than
rendered images. The frontend renders them; an MCP client can summarize them.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from .analysis import _json_safe
from .store import DatasetError, DatasetStore

ChartType = Literal["bar", "pie", "histogram", "scatter", "line"]


def build_chart(
    store: DatasetStore,
    name: str,
    chart_type: ChartType,
    x: str | None = None,
    y: str | None = None,
    bins: int = 10,
    top: int = 20,
) -> dict[str, Any]:
    df = store.frame(name)

    def require(col: str | None, role: str) -> str:
        if not col:
            raise DatasetError(f"Chart type '{chart_type}' requires an '{role}' column.")
        if col not in df.columns:
            raise DatasetError(
                f"Column '{col}' not in '{name}'. Columns: "
                f"{', '.join(map(str, df.columns))}."
            )
        return col

    if chart_type in ("bar", "pie"):
        xcol = require(x, "x")
        if y:
            ycol = require(y, "y")
            agg = df.groupby(xcol, dropna=False)[ycol].sum().sort_values(ascending=False)
            y_label = f"sum({ycol})"
        else:
            agg = df.groupby(xcol, dropna=False).size().sort_values(ascending=False)
            y_label = "count"
        agg = agg.head(top)
        data = [{"label": _json_safe(idx), "value": _json_safe(val)} for idx, val in agg.items()]
        return _spec(chart_type, name, data, x_label=xcol, y_label=y_label)

    if chart_type == "histogram":
        xcol = require(x, "x")
        series = pd.to_numeric(df[xcol], errors="coerce").dropna()
        if series.empty:
            raise DatasetError(f"Column '{xcol}' has no numeric values to bin.")
        counts, edges = np.histogram(series, bins=bins)
        data = [
            {
                "label": f"{round(float(edges[i]), 2)}–{round(float(edges[i + 1]), 2)}",
                "value": int(counts[i]),
            }
            for i in range(len(counts))
        ]
        return _spec("bar", name, data, x_label=xcol, y_label="count", subtype="histogram")

    if chart_type in ("scatter", "line"):
        xcol = require(x, "x")
        ycol = require(y, "y")
        sub = df[[xcol, ycol]].dropna()
        if chart_type == "line":
            sub = sub.sort_values(xcol)
        points = [
            {"x": _json_safe(rx), "y": _json_safe(ry)}
            for rx, ry in zip(sub[xcol], sub[ycol])
        ]
        return _spec(chart_type, name, points, x_label=xcol, y_label=ycol)

    raise DatasetError(f"Unknown chart type '{chart_type}'.")


def _spec(
    chart_type: str,
    dataset: str,
    data: list[dict[str, Any]],
    *,
    x_label: str,
    y_label: str,
    subtype: str | None = None,
) -> dict[str, Any]:
    title = f"{y_label} by {x_label}" if chart_type in ("bar", "pie") else f"{y_label} vs {x_label}"
    return {
        "dataset": dataset,
        "type": chart_type,
        "subtype": subtype,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "data": data,
    }
