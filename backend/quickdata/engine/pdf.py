"""Render a report dict (from :mod:`quickdata.engine.report`) to a PDF.

Uses fpdf2: ``write_html`` for narrative text + tables, and hand-drawn bar /
scatter charts (no native deps, unlike WeasyPrint/cairosvg). fpdf2 core fonts
are latin-1, so all text is sanitized to ASCII first.
"""

from __future__ import annotations

import re
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ACCENT = (99, 102, 241)

_UNICODE = {
    "×": "x", "≥": ">=", "≤": "<=", "↔": "<->", "→": "->", "←": "<-",
    "—": "-", "–": "-", "•": "-", "≈": "~", "…": "...",
    "“": '"', "”": '"', "‘": "'", "’": "'", "·": "-",
}


def _ascii(text: str) -> str:
    for uni, rep in _UNICODE.items():
        text = text.replace(uni, rep)
    return text.encode("latin-1", "replace").decode("latin-1")


def _esc(text: str) -> str:
    return _ascii(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """Escape, then convert **bold** and strip `code` backticks for write_html."""
    s = _esc(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return s


def _md_to_html(markdown: str) -> str:
    """Markdown subset -> fpdf2-friendly HTML (headings, bold, lists, tables, code)."""
    lines = markdown.splitlines()
    html: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("_chart:"):  # chart placeholders -> charts section
            i += 1
            continue

        if line.startswith("```"):
            buf: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(_esc(lines[i]))
                i += 1
            i += 1
            # render as a wrapped paragraph (pre doesn't wrap long lines well)
            html.append('<font face="courier" size="8"><p>' + "<br>".join(buf) + "</p></font>")
            continue

        # table: header row + separator
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?$", lines[i + 1].strip()):
            def cells(row: str) -> list[str]:
                return [c.strip() for c in row.strip().strip("|").split("|")]

            headers = cells(line)
            i += 2
            body: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                body.append(cells(lines[i]))
                i += 1
            th = "".join(f"<th>{_inline(h)}</th>" for h in headers)
            trs = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body
            )
            html.append(f'<table border="1"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
            continue

        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            if len(h[1]) == 1:  # the document title — already rendered manually
                i += 1
                continue
            level = min(len(h[1]), 3) + 1  # ## -> h3 etc.
            html.append(f"<h{level}>{_inline(h[2])}</h{level}>")
            i += 1
            continue

        # whole-line italic, e.g. "_30271 rows x 21 columns_"
        em = re.match(r"^_(.+)_$", line.strip())
        if em:
            html.append(f"<p><i>{_inline(em[1])}</i></p>")
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append("<li>" + _inline(re.sub(r"^\s*[-*]\s+", "", lines[i])) + "</li>")
                i += 1
            html.append("<ul>" + "".join(items) + "</ul>")
            continue

        if line.strip():
            html.append(f"<p>{_inline(line)}</p>")
        i += 1

    return "\n".join(html)


def report_to_pdf(report: dict[str, Any]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 10, _ascii(f"Data report — {report['dataset']}"),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=11)

    pdf.write_html(_md_to_html(report["markdown"]))

    charts = [c for c in report.get("charts", []) if c.get("data")]
    if charts:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 9, "Charts", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for spec in charts:
            _draw_chart(pdf, spec)

    return bytes(pdf.output())


# ------------------------------------------------------------------- charting


def _ensure_space(pdf: FPDF, height: float) -> None:
    if pdf.get_y() + height > pdf.h - pdf.b_margin:
        pdf.add_page()


def _draw_chart(pdf: FPDF, spec: dict[str, Any]) -> None:
    data = spec["data"]
    _ensure_space(pdf, 16)
    pdf.set_font("Helvetica", "B", 11)
    pdf.multi_cell(0, 7, _ascii(spec.get("title", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=9)
    if "label" in data[0]:
        _draw_bars(pdf, data)
    elif "x" in data[0]:
        _draw_scatter(pdf, spec, data)
    pdf.ln(5)


def _draw_bars(pdf: FPDF, data: list[dict[str, Any]]) -> None:
    items = data[:12]
    maxv = max((abs(d["value"]) for d in items), default=1) or 1
    left = pdf.l_margin
    label_w, bar_max, val_w, row_h = 50.0, 105.0, 25.0, 6.0
    for d in items:
        _ensure_space(pdf, row_h)
        y = pdf.get_y()
        pdf.set_xy(left, y)
        pdf.cell(label_w, row_h, _trunc(str(d["label"]), 28))
        w = (abs(d["value"]) / maxv) * bar_max
        pdf.set_fill_color(*ACCENT)
        pdf.rect(left + label_w, y + 1, max(w, 0.6), row_h - 2, style="F")
        pdf.set_xy(left + label_w + bar_max + 2, y)
        pdf.cell(val_w, row_h, _fmt(d["value"]))
        pdf.set_y(y + row_h)


def _draw_scatter(pdf: FPDF, spec: dict[str, Any], data: list[dict[str, Any]]) -> None:
    pts = [p for p in data if isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float))]
    if not pts:
        return
    box_h = 70.0
    _ensure_space(pdf, box_h + 10)
    left = pdf.l_margin + 14
    top = pdf.get_y()
    box_w = pdf.w - pdf.r_margin - left
    xs = [p["x"] for p in pts]
    ys = [p["y"] for p in pts]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)

    def sx(x: float) -> float:
        return left + (x - xmin) / ((xmax - xmin) or 1) * box_w

    def sy(y: float) -> float:
        return top + box_h - (y - ymin) / ((ymax - ymin) or 1) * box_h

    pdf.set_draw_color(200, 200, 200)
    pdf.rect(left, top, box_w, box_h)
    pdf.set_fill_color(*ACCENT)
    for p in pts[:4000]:
        pdf.rect(sx(p["x"]) - 0.4, sy(p["y"]) - 0.4, 0.8, 0.8, style="F")
    pdf.set_xy(left, top + box_h + 1)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(box_w, 5, _ascii(f"x: {spec.get('x_label', '')}   y: {spec.get('y_label', '')}"))
    pdf.set_y(top + box_h + 7)


def _trunc(s: str, n: int) -> str:
    s = _ascii(s)
    return s if len(s) <= n else s[: n - 2] + "..."


def _fmt(v: Any) -> str:
    if isinstance(v, (int, float)):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return _ascii(str(v))
