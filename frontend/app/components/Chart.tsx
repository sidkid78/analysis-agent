"use client";

import type { ChartSpec } from "../lib/api";

// Dependency-free chart rendering: bars/histograms as flex rows, scatter/line
// as inline SVG. Keeps the bundle lean and avoids charting-lib version churn.

const ACCENT = "#6366f1";

function isCategorical(
  d: ChartSpec["data"],
): d is Array<{ label: string; value: number }> {
  return d.length === 0 || "label" in d[0];
}

export function Chart({ spec }: { spec: ChartSpec }) {
  return (
    <div className="rounded-xl border border-black/10 bg-white/60 p-4 dark:border-white/10 dark:bg-white/5">
      <div className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-200">
        {spec.title}
      </div>
      {isCategorical(spec.data) ? (
        <BarChart data={spec.data} />
      ) : (
        <ScatterChart
          data={spec.data as Array<{ x: number; y: number }>}
          xLabel={spec.x_label}
          yLabel={spec.y_label}
          line={spec.type === "line"}
        />
      )}
    </div>
  );
}

function BarChart({ data }: { data: Array<{ label: string; value: number }> }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="flex flex-col gap-1.5">
      {data.map((d, i) => (
        <div key={`${d.label}-${i}`} className="flex items-center gap-2 text-xs">
          <div className="w-32 shrink-0 truncate text-right text-zinc-500 dark:text-zinc-400">
            {d.label}
          </div>
          <div className="relative h-5 flex-1 rounded bg-black/5 dark:bg-white/5">
            <div
              className="absolute inset-y-0 left-0 rounded"
              style={{
                width: `${Math.max((d.value / max) * 100, 1)}%`,
                background: ACCENT,
              }}
            />
          </div>
          <div className="w-20 shrink-0 tabular-nums text-zinc-700 dark:text-zinc-300">
            {formatNum(d.value)}
          </div>
        </div>
      ))}
    </div>
  );
}

function ScatterChart({
  data,
  xLabel,
  yLabel,
  line,
}: {
  data: Array<{ x: number; y: number }>;
  xLabel: string;
  yLabel: string;
  line: boolean;
}) {
  const W = 460;
  const H = 280;
  const pad = 40;
  const xs = data.map((d) => d.x);
  const ys = data.map((d) => d.y);
  const xMin = Math.min(...xs),
    xMax = Math.max(...xs);
  const yMin = Math.min(...ys),
    yMax = Math.max(...ys);
  const sx = (x: number) =>
    pad + ((x - xMin) / (xMax - xMin || 1)) * (W - 2 * pad);
  const sy = (y: number) =>
    H - pad - ((y - yMin) / (yMax - yMin || 1)) * (H - 2 * pad);

  const path = data
    .map((d, i) => `${i === 0 ? "M" : "L"} ${sx(d.x).toFixed(1)} ${sy(d.y).toFixed(1)}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${yLabel} vs ${xLabel}`}>
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="currentColor" strokeOpacity={0.2} />
      <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke="currentColor" strokeOpacity={0.2} />
      {line && <path d={path} fill="none" stroke={ACCENT} strokeWidth={1.5} />}
      {data.map((d, i) => (
        <circle key={i} cx={sx(d.x)} cy={sy(d.y)} r={2.5} fill={ACCENT} fillOpacity={0.65} />
      ))}
      <text x={W / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="currentColor" fillOpacity={0.6}>
        {xLabel}
      </text>
      <text x={12} y={H / 2} textAnchor="middle" fontSize={11} fill="currentColor" fillOpacity={0.6} transform={`rotate(-90 12 ${H / 2})`}>
        {yLabel}
      </text>
    </svg>
  );
}

function formatNum(n: number): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
