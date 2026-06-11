"""Analysis playbooks: reusable, multi-step recipes.

A playbook composes engine ops into a structured result — markdown ``sections``
plus ``charts`` — so it can be rendered in the UI, returned by an MCP prompt, or
summarized by the agent. This is the "prompts are recipes for repeat solutions"
idea made concrete.
"""

from __future__ import annotations

from typing import Any, Callable

from . import analysis, charts, quality
from .store import DatasetError, DatasetStore


def _section(title: str, body: str) -> dict[str, str]:
    return {"title": title, "body": body.strip()}


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return "\n".join([head, sep, body]) if rows else "_none_"


def first_look(store: DatasetStore, name: str) -> dict[str, Any]:
    b = analysis.breakdown(store, name)
    sug = analysis.suggest_analysis(store, name)
    sections = [
        _section(
            "Overview",
            f"**{b['rows']} rows × {len(b['columns'])} columns**\n\n"
            f"- Numeric: {', '.join(b['numerical_columns']) or '—'}\n"
            f"- Categorical: {', '.join(b['categorical_columns']) or '—'}\n"
            f"- Datetime: {', '.join(b['datetime_columns']) or '—'}",
        ),
        _section(
            "Columns",
            _md_table(
                ["column", "type", "nulls", "unique"],
                [[c["name"], c["kind"], c["null_count"], c["unique_count"]] for c in b["columns"]],
            ),
        ),
    ]

    charts_out: list[dict[str, Any]] = []
    if b["categorical_columns"]:
        col = sug["suggestions"][0]["column"] if sug["suggestions"] and sug["suggestions"][0].get("column") else b["categorical_columns"][0]
        try:
            charts_out.append(charts.build_chart(store, name, "bar", x=col))
        except DatasetError:
            pass
    elif b["numerical_columns"]:
        charts_out.append(charts.build_chart(store, name, "histogram", x=b["numerical_columns"][0]))

    next_steps = "\n".join(f"- {s['title']} — {s['why']}" for s in sug["suggestions"][:4]) or "_no suggestions_"
    sections.append(_section("Suggested next steps", next_steps))

    return {
        "playbook": "first_look",
        "dataset": name,
        "summary": f"{name}: {b['rows']} rows, {len(b['columns'])} columns.",
        "sections": sections,
        "charts": charts_out,
    }


def data_quality_audit(store: DatasetStore, name: str) -> dict[str, Any]:
    p = quality.profile(store, name)
    issue_rows = [[i["severity"], i["issue"], f"`{i['fix']}`"] for i in p["issues"]]
    fixes = [i["fix"] for i in p["issues"] if i["severity"] == "warning"]
    sections = [
        _section(
            "Quality score",
            f"**{p['quality_score']}/100** — {p['rows']} rows, "
            f"{p['duplicate_rows']} duplicate row(s), {len(p['issues'])} issue(s) flagged.",
        ),
        _section("Issues", _md_table(["severity", "issue", "suggested fix"], issue_rows)),
    ]
    if fixes:
        sections.append(
            _section(
                "Recommended cleaning",
                "Apply with one call:\n\n```\nclean_dataset('"
                + name
                + "', ["
                + ", ".join(f'"{f}"' for f in fixes)
                + "])\n```",
            )
        )
    return {
        "playbook": "data_quality_audit",
        "dataset": name,
        "summary": f"{name}: quality {p['quality_score']}/100, {len(p['issues'])} issue(s).",
        "sections": sections,
        "charts": [],
    }


def correlation_deep_dive(store: DatasetStore, name: str, threshold: float = 0.3) -> dict[str, Any]:
    try:
        result = analysis.find_correlations(store, name, threshold)
    except DatasetError as exc:
        return {
            "playbook": "correlation_deep_dive",
            "dataset": name,
            "summary": str(exc),
            "sections": [_section("Not applicable", str(exc))],
            "charts": [],
        }
    pairs = result["correlations"]
    rows = [[p["x"], p["y"], p["r"], f"{p['strength']} {p['direction']}"] for p in pairs]
    sections = [
        _section(
            "Correlations",
            f"Found **{len(pairs)}** pair(s) with |r| ≥ {threshold} across "
            f"{len(result['numerical_columns'])} numeric columns.\n\n"
            + _md_table(["x", "y", "r", "strength"], rows),
        )
    ]
    charts_out: list[dict[str, Any]] = []
    for p in pairs[:2]:
        try:
            charts_out.append(charts.build_chart(store, name, "scatter", x=p["x"], y=p["y"]))
        except DatasetError:
            pass
    summary = (
        f"Strongest: {pairs[0]['x']} ↔ {pairs[0]['y']} (r={pairs[0]['r']})."
        if pairs
        else "No notable correlations."
    )
    return {
        "playbook": "correlation_deep_dive",
        "dataset": name,
        "summary": summary,
        "sections": sections,
        "charts": charts_out,
    }


PLAYBOOKS: dict[str, Callable[..., dict[str, Any]]] = {
    "first_look": first_look,
    "data_quality_audit": data_quality_audit,
    "correlation_deep_dive": correlation_deep_dive,
}


def run(store: DatasetStore, playbook: str, name: str) -> dict[str, Any]:
    fn = PLAYBOOKS.get(playbook)
    if fn is None:
        raise DatasetError(
            f"Unknown playbook '{playbook}'. Available: {', '.join(PLAYBOOKS)}."
        )
    return fn(store, name)


def to_markdown(result: dict[str, Any]) -> str:
    """Render a playbook result as a markdown document."""
    lines = [f"## {result['playbook'].replace('_', ' ').title()} — `{result['dataset']}`", ""]
    for sec in result["sections"]:
        lines += [f"### {sec['title']}", "", sec["body"], ""]
    for chart in result.get("charts", []):
        lines.append(f"_chart: {chart['title']}_")
    return "\n".join(lines)
