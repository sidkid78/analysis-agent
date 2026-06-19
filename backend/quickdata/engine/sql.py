"""Ad-hoc SQL queries over loaded datasets.

Runs SQL against an *ephemeral* in-memory SQLite database built fresh on each
call: every requested dataset is registered as a table, the query runs, and the
database is thrown away. The DataFrames in the store stay the single source of
truth — unlike a persistent SQL mirror, there is nothing to keep in sync.

Only read-only statements (``SELECT`` / ``WITH``) are allowed. Because every
loaded dataset is registered by default, queries can JOIN across datasets.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

import pandas as pd

from .analysis import _json_safe
from .store import DatasetError, DatasetStore

_NON_IDENT_RE = re.compile(r"\W+")


def _table_name(name: str) -> str:
    """Turn a dataset name into a safe SQL table identifier."""
    t = _NON_IDENT_RE.sub("_", name).strip("_")
    if not t:
        t = "dataset"
    if t[0].isdigit():
        t = f"t_{t}"
    return t


def _is_read_only(sql: str) -> bool:
    """True if the statement is a read-only SELECT or WITH (CTE) query."""
    # Strip leading comments/whitespace, then require SELECT or WITH at the start.
    stripped = re.sub(r"^(?:\s|--[^\n]*\n|/\*.*?\*/)+", "", sql, flags=re.DOTALL)
    return re.match(r"(?is)(select|with)\b", stripped) is not None


def run_sql(
    store: DatasetStore,
    sql: str,
    datasets: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Run a read-only SQL query against one or more loaded datasets.

    Args:
        store: The dataset store.
        sql: A single SELECT/WITH statement. Reference datasets by their table
            name (see the returned ``tables`` mapping; usually identical to the
            dataset name).
        datasets: Dataset names to register as tables. Defaults to all loaded,
            which lets a query JOIN across datasets.
        limit: Max rows returned to the caller (the query itself is unbounded).
    """
    if not sql or not sql.strip():
        raise DatasetError("Empty SQL query.")
    if not _is_read_only(sql):
        raise DatasetError(
            "Only read-only SELECT/WITH queries are allowed (no INSERT/UPDATE/"
            "DELETE/DROP/etc.)."
        )

    names = datasets if datasets is not None else store.names()
    if not names:
        raise DatasetError("No datasets loaded to query.")

    tables: dict[str, str] = {}
    by_table: dict[str, str] = {}
    for n in names:
        store.frame(n)  # validates existence (raises DatasetError if missing)
        t = _table_name(n)
        if t in by_table:
            raise DatasetError(
                f"Datasets '{by_table[t]}' and '{n}' both map to table '{t}'. "
                f"Pass `datasets=[...]` to query them one at a time."
            )
        tables[n] = t
        by_table[t] = n

    conn = sqlite3.connect(":memory:")
    try:
        for n in names:
            store.frame(n).to_sql(tables[n], conn, index=False, if_exists="replace")
        try:
            result = pd.read_sql_query(sql, conn)
        except Exception as exc:  # sqlite/pandas surface a variety of error types
            raise DatasetError(f"SQL error: {exc}") from exc
    finally:
        conn.close()

    total = int(len(result))
    result = result.head(max(1, int(limit)))
    rows = [
        {k: _json_safe(v) for k, v in rec.items()}
        for rec in result.to_dict(orient="records")
    ]
    return {
        "sql": sql,
        "tables": tables,
        "columns": [str(c) for c in result.columns],
        "result_rows": total,
        "returned_rows": len(rows),
        "rows": rows,
    }
