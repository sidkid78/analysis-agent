"""Shared analysis engine.

Everything in here is plain Python + pandas with no MCP or HTTP dependency, so
it can be imported and unit-tested in isolation and reused by any transport.
"""

from .store import DatasetStore, DatasetInfo, ColumnInfo, default_store
from . import analysis, charts, query, quality, playbooks, report, pdf

__all__ = [
    "DatasetStore",
    "DatasetInfo",
    "ColumnInfo",
    "default_store",
    "analysis",
    "charts",
    "query",
    "quality",
    "playbooks",
    "report",
    "pdf",
]
