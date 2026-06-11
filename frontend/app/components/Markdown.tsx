"use client";

import { Fragment, type ReactNode } from "react";

// Minimal markdown renderer for playbook/report bodies: headings, bold,
// inline code, lists, code fences, and pipe tables. No external deps.

function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Split on **bold** and `code`, preserving delimiters.
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  parts.forEach((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) {
      nodes.push(<strong key={`${keyBase}-${i}`}>{p.slice(2, -2)}</strong>);
    } else if (/^`[^`]+`$/.test(p)) {
      nodes.push(
        <code key={`${keyBase}-${i}`} className="rounded bg-black/[.06] px-1 py-0.5 text-[0.85em] dark:bg-white/10">
          {p.slice(1, -1)}
        </code>,
      );
    } else if (p) {
      nodes.push(<Fragment key={`${keyBase}-${i}`}>{p}</Fragment>);
    }
  });
  return nodes;
}

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code fence
    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++; // closing fence
      blocks.push(
        <pre key={key++} className="overflow-x-auto rounded-lg bg-black/[.05] p-3 text-xs dark:bg-white/5">
          {buf.join("\n")}
        </pre>,
      );
      continue;
    }

    // Table: a header row followed by a separator row
    if (line.startsWith("|") && i + 1 < lines.length && /^\|[\s:|-]+\|?$/.test(lines[i + 1].trim())) {
      const cells = (row: string) =>
        row.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const headers = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={key++} className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                {headers.map((h, hi) => (
                  <th key={hi} className="border-b border-black/15 px-2 py-1 text-left font-semibold dark:border-white/15">
                    {inline(h, `h${hi}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci} className="border-b border-black/5 px-2 py-1 dark:border-white/5">
                      {inline(c, `c${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // Headings
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const size = ["text-base", "text-sm", "text-sm", "text-xs"][h[1].length - 1];
      blocks.push(
        <p key={key++} className={`${size} mt-1 font-semibold`}>
          {inline(h[2], `head${key}`)}
        </p>,
      );
      i++;
      continue;
    }

    // List items (consecutive)
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={key++} className="ml-4 list-disc space-y-0.5">
          {items.map((it, ii) => (
            <li key={ii}>{inline(it, `li${key}-${ii}`)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    blocks.push(
      <p key={key++} className="leading-relaxed">
        {inline(line, `p${key}`)}
      </p>,
    );
    i++;
  }

  return <div className="flex flex-col gap-2 text-sm">{blocks}</div>;
}
