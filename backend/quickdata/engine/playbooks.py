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


def executive_summary(store: DatasetStore, name: str) -> dict[str, Any]:
    """A C-suite narrative: takeaways, key breakdown, trend, relationships, and
    a data-confidence note — composed from the other engine ops."""
    b = analysis.breakdown(store, name)
    sug = analysis.suggest_analysis(store, name)
    charts_out: list[dict[str, Any]] = []
    highlights: list[str] = []

    sections = [
        _section(
            "Headline",
            f"**{name}** covers **{b['rows']:,} records** across "
            f"**{len(b['columns'])} fields** "
            f"({len(b['numerical_columns'])} numeric, "
            f"{len(b['categorical_columns'])} categorical, "
            f"{len(b['datetime_columns'])} datetime).",
        )
    ]

    # Composition by the top suggested category.
    seg_cols = [
        s["column"] for s in sug["suggestions"]
        if s["operation"] == "segment" and s.get("column")
    ]
    if seg_cols:
        seg = analysis.segment_by_column(store, name, seg_cols[0], top=5)
        if seg["segments"]:
            top_seg = seg["segments"][0]
            highlights.append(
                f"'{top_seg['value']}' leads **{seg['column']}** with "
                f"{top_seg['count']:,} records."
            )
            sections.append(
                _section(
                    f"Breakdown by {seg['column']}",
                    _md_table(
                        [seg["column"], "records"],
                        [[s["value"], f"{s['count']:,}"] for s in seg["segments"]],
                    ),
                )
            )
            try:
                charts_out.append(charts.build_chart(store, name, "bar", x=seg["column"]))
            except DatasetError:
                pass

    # Trend over time, when a date column is present.
    try:
        tr = analysis.trend_analysis(store, name)
        arrow = {"rising": "↑", "falling": "↓", "flat": "→"}[tr["direction"]]
        pct = f"{tr['change_pct']:+.1f}%" if tr["change_pct"] is not None else "n/a"
        highlights.append(f"{tr['metric']} is **{tr['direction']}** {arrow} ({pct}).")
        sections.append(
            _section(
                "Trend",
                f"Across **{tr['periods']}** {tr['frequency']} periods, "
                f"{tr['metric']} moved from {tr['first']} to {tr['last']} ({pct}). "
                f"Peak {tr['peak']['value']} on {tr['peak']['period']}; "
                f"low {tr['trough']['value']} on {tr['trough']['period']}.",
            )
        )
        charts_out.append(tr["chart"])
    except DatasetError:
        pass

    # Key relationships.
    try:
        corr = analysis.find_correlations(store, name, threshold=0.5)
        if corr["correlations"]:
            top = corr["correlations"][0]
            highlights.append(
                f"**{top['x']}** and **{top['y']}** move together "
                f"({top['strength']} {top['direction']}, r={top['r']})."
            )
            sections.append(
                _section(
                    "Key relationships",
                    _md_table(
                        ["x", "y", "r", "strength"],
                        [
                            [c["x"], c["y"], c["r"], f"{c['strength']} {c['direction']}"]
                            for c in corr["correlations"][:5]
                        ],
                    ),
                )
            )
    except DatasetError:
        pass

    # Data confidence from the quality score.
    q = quality.profile(store, name)
    score = q["quality_score"]
    confidence = "high" if score >= 85 else "moderate" if score >= 60 else "low"
    sections.append(
        _section(
            "Data confidence",
            f"Quality score **{score}/100** ({confidence}); {q['duplicate_rows']} "
            f"duplicate row(s), {len(q['issues'])} issue(s) flagged. "
            + (
                "Findings are reliable."
                if confidence == "high"
                else "Validate key figures before circulating."
            ),
        )
    )

    takeaways = "\n".join(f"- {h}" for h in highlights) or (
        "- Dataset loaded; no standout patterns detected automatically."
    )
    sections.insert(1, _section("Key takeaways", takeaways))

    return {
        "playbook": "executive_summary",
        "dataset": name,
        "summary": highlights[0] if highlights else f"{name}: {b['rows']} records summarized.",
        "sections": sections,
        "charts": charts_out,
    }


PLAYBOOKS: dict[str, Callable[..., dict[str, Any]]] = {
    "first_look": first_look,
    "data_quality_audit": data_quality_audit,
    "correlation_deep_dive": correlation_deep_dive,
    "executive_summary": executive_summary,
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
