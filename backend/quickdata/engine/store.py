"""In-memory dataset store and schema classification.

Datasets are held as pandas DataFrames keyed by name. A process-wide
``default_store`` is shared by the MCP server and the HTTP API so that, within a
single process, a dataset loaded through one transport is visible to the other.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

ColumnKind = Literal["numerical", "categorical", "datetime", "boolean"]


@dataclass
class ColumnInfo:
    name: str
    dtype: str
    kind: ColumnKind
    null_count: int
    unique_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "kind": self.kind,
            "null_count": self.null_count,
            "unique_count": self.unique_count,
        }


@dataclass
class DatasetInfo:
    name: str
    rows: int
    columns: list[ColumnInfo] = field(default_factory=list)
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rows": self.rows,
            "column_count": len(self.columns),
            "columns": [c.to_dict() for c in self.columns],
            "source": self.source,
        }

    def columns_of_kind(self, *kinds: ColumnKind) -> list[str]:
        return [c.name for c in self.columns if c.kind in kinds]


def _classify(series: pd.Series) -> ColumnKind:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numerical"
    return "categorical"


class DatasetError(Exception):
    """Raised for user-facing dataset problems (missing dataset, bad column)."""


class DatasetStore:
    def __init__(self) -> None:
        self._frames: dict[str, pd.DataFrame] = {}
        self._sources: dict[str, str | None] = {}

    # ------------------------------------------------------------------ loading
    def load_dataframe(
        self, name: str, df: pd.DataFrame, source: str | None = None
    ) -> DatasetInfo:
        if df.empty and len(df.columns) == 0:
            raise DatasetError("Refusing to load an empty dataset.")
        self._frames[name] = df
        self._sources[name] = source
        return self.info(name)

    def load_records(
        self, name: str, records: list[dict[str, Any]], source: str | None = None
    ) -> DatasetInfo:
        return self.load_dataframe(name, pd.json_normalize(records), source)

    def load_file(self, name: str, path: str | Path) -> DatasetInfo:
        p = Path(path)
        if not p.exists():
            raise DatasetError(f"File not found: {p}")
        df = self._read_frame(p.read_bytes(), p.suffix, p.name)
        return self.load_dataframe(name, df, source=str(p))

    def load_bytes(
        self, name: str, raw: bytes, filename: str
    ) -> DatasetInfo:
        suffix = Path(filename).suffix
        df = self._read_frame(raw, suffix, filename)
        return self.load_dataframe(name, df, source=filename)

    @staticmethod
    def _read_frame(raw: bytes, suffix: str, filename: str) -> pd.DataFrame:
        suffix = suffix.lower()
        if suffix == ".json":
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                # A single object, or {"records": [...]} style envelopes.
                for key in ("records", "data", "rows", "items"):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
                else:
                    data = [data]
            return pd.json_normalize(data)
        if suffix in (".csv", ".tsv", ".txt"):
            sep = "\t" if suffix == ".tsv" else ","
            return pd.read_csv(io.BytesIO(raw), sep=sep)
        raise DatasetError(
            f"Unsupported file type '{suffix or filename}'. Use .json, .csv, or .tsv."
        )

    # ----------------------------------------------------------------- accessors
    def names(self) -> list[str]:
        return sorted(self._frames)

    def has(self, name: str) -> bool:
        return name in self._frames

    def frame(self, name: str) -> pd.DataFrame:
        if name not in self._frames:
            raise DatasetError(
                f"No dataset named '{name}'. Loaded datasets: "
                f"{', '.join(self.names()) or '(none)'}."
            )
        return self._frames[name]

    def remove(self, name: str) -> None:
        self._frames.pop(name, None)
        self._sources.pop(name, None)

    def info(self, name: str) -> DatasetInfo:
        df = self.frame(name)
        columns = [
            ColumnInfo(
                name=str(col),
                dtype=str(df[col].dtype),
                kind=_classify(df[col]),
                null_count=int(df[col].isna().sum()),
                unique_count=int(df[col].nunique(dropna=True)),
            )
            for col in df.columns
        ]
        return DatasetInfo(
            name=name, rows=int(len(df)), columns=columns, source=self._sources.get(name)
        )

    def list_info(self) -> list[DatasetInfo]:
        return [self.info(n) for n in self.names()]


# Process-wide store shared by all transports in this process.
default_store = DatasetStore()
