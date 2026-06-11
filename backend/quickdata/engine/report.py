"""Compile playbooks into a single shareable report (Markdown / HTML)."""

from __future__ import annotations

from typing import Any

from . import playbooks
from .store import DatasetStore

_REPORT_PLAYBOOKS = ["first_look", "data_quality_audit", "correlation_deep_dive"]


def generate_report(store: DatasetStore, name: str) -> dict[str, Any]:
    info = store.info(name)
    results = [playbooks.run(store, pb, name) for pb in _REPORT_PLAYBOOKS]

    lines = [
        f"# Data report — {name}",
        "",
        f"_{info.rows} rows × {len(info.columns)} columns_",
        "",
        "## Summary",
        "",
    ]
    for r in results:
        lines.append(f"- **{r['playbook'].replace('_', ' ').title()}**: {r['summary']}")
    lines.append("")

    charts: list[dict[str, Any]] = []
    for r in results:
        lines += ["", playbooks.to_markdown(r), ""]
        charts.extend(r.get("charts", []))

    markdown = "\n".join(lines)
    return {
        "dataset": name,
        "markdown": markdown,
        "html": _markdown_to_html(markdown),
        "charts": charts,
    }


def _markdown_to_html(md: str) -> str:
    """Minimal markdown→HTML (headings, bold, tables, code) — no extra deps."""
    html: list[str] = []
    in_table = False
    in_code = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            html.append("<pre>" if in_code else "</pre>")
            continue
        if in_code:
            html.append(_escape(line))
            continue
        if line.startswith("| "):
            cells = [c.strip() for c in line.strip("| ").split("|")]
            if set("".join(cells)) <= {"-", " "}:
                continue  # separator row
            if not in_table:
                html.append("<table>")
                in_table = True
            tag = "td"
            html.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            html.append("</table>")
            in_table = False
        if line.startswith("### "):
            html.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            html.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            html.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("- "):
            html.append(f"<li>{_inline(line[2:])}</li>")
        elif line:
            html.append(f"<p>{_inline(line)}</p>")
    if in_table:
        html.append("</table>")
    return "\n".join(html)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    s = _escape(s)
    # bold then inline code
    import re

    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s
