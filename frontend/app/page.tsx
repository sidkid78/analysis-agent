"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type Breakdown,
  type ChartSpec,
  type CorrelationResult,
  type DatasetInfo,
  type PlaybookResult,
  type SegmentResult,
  type Suggestion,
  type Suggestions,
} from "./lib/api";
import { Chart } from "./components/Chart";
import { ChatPanel } from "./components/ChatPanel";
import { Markdown } from "./components/Markdown";

export default function Home() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [samples, setSamples] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestions | null>(null);
  const [correlations, setCorrelations] = useState<CorrelationResult | null>(null);
  const [segment, setSegment] = useState<SegmentResult | null>(null);
  const [chart, setChart] = useState<ChartSpec | null>(null);
  const [playbook, setPlaybook] = useState<PlaybookResult | null>(null);
  const [threshold, setThreshold] = useState(0.5);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshDatasets = useCallback(async () => {
    const res = await run(() => api.listDatasets());
    if (res) setDatasets(res.datasets);
  }, [run]);

  // The agent shares the backend's dataset store, so reflect anything it loaded
  // in the sidebar (the user can click it to inspect with the manual tools).
  const onAgentActivity = useCallback(async () => {
    const res = await api.listDatasets().catch(() => null);
    if (res) setDatasets(res.datasets);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        const [s, d] = await Promise.all([api.listSamples(), api.listDatasets()]);
        setSamples(s.samples);
        setDatasets(d.datasets);
      } catch {
        setOffline(true);
      }
    })();
  }, []);

  const selectDataset = useCallback(
    async (name: string) => {
      setSelected(name);
      setSegment(null);
      setChart(null);
      setCorrelations(null);
      setPlaybook(null);
      const res = await run(async () => ({
        breakdown: await api.breakdown(name),
        suggestions: await api.suggestions(name),
      }));
      if (res) {
        setBreakdown(res.breakdown);
        setSuggestions(res.suggestions);
      }
    },
    [run],
  );

  async function loadSample(filename: string) {
    const info = await run(() => api.loadSample(filename));
    if (info) {
      await refreshDatasets();
      await selectDataset(info.name);
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const info = await run(() => api.upload(file));
    if (fileRef.current) fileRef.current.value = "";
    if (info) {
      await refreshDatasets();
      await selectDataset(info.name);
    }
  }

  async function runCorrelations() {
    if (!selected) return;
    const res = await run(() => api.correlations(selected, threshold));
    if (res) setCorrelations(res);
  }

  async function runSegment(column: string) {
    if (!selected) return;
    const res = await run(() => api.segment(selected, column));
    if (res) {
      setSegment(res);
      setChart(null);
    }
  }

  async function runChart(body: Parameters<typeof api.chart>[1]) {
    if (!selected) return;
    const res = await run(() => api.chart(selected, body));
    if (res) setChart(res);
  }

  async function runPlaybook(pb: string) {
    if (!selected) return;
    const res = await run(() => api.playbook(selected, pb));
    if (res) setPlaybook(res);
  }

  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function downloadReportPdf() {
    if (!selected) return;
    const blob = await run(() => api.reportPdf(selected));
    if (blob) triggerDownload(blob, `${selected}-report.pdf`);
  }

  async function downloadReportMarkdown() {
    if (!selected) return;
    const res = await run(() => api.report(selected));
    if (res) triggerDownload(new Blob([res.markdown], { type: "text/markdown" }), `${selected}-report.md`);
  }

  async function applySuggestion(s: Suggestion) {
    if (!selected) return;
    if (s.operation === "segment" && s.column) return runSegment(s.column);
    if (s.operation === "correlations") return runCorrelations();
    if (s.operation === "chart" && s.column)
      return runChart({ chart_type: "histogram", x: s.column });
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[88rem] flex-col gap-6 px-6 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Quick Data</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Load a JSON/CSV dataset, then explore it. Same engine powers the MCP
            server.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <span
            className={`inline-block h-2 w-2 rounded-full ${offline ? "bg-red-500" : "bg-emerald-500"}`}
          />
          {offline ? "API offline" : "API connected"} · {api.base}
        </div>
      </header>

      {offline && (
        <div className="rounded-lg border border-amber-300/50 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          Can&apos;t reach the backend. Start it with{" "}
          <code className="rounded bg-black/10 px-1 dark:bg-white/10">
            uv run quickdata-api
          </code>{" "}
          in <code>backend/</code>.
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-300/50 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-6 xl:flex-row">
        {/* Sidebar */}
        <aside className="flex flex-col gap-5 xl:w-60 xl:shrink-0">
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Sample datasets
            </h2>
            <div className="flex flex-col gap-1.5">
              {samples.map((s) => (
                <button
                  key={s}
                  onClick={() => loadSample(s)}
                  disabled={busy}
                  className="rounded-lg border border-black/10 px-3 py-2 text-left text-sm transition hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-indigo-500/10"
                >
                  {s}
                </button>
              ))}
              {samples.length === 0 && !offline && (
                <span className="text-xs text-zinc-400">No samples found.</span>
              )}
            </div>
            <label className="mt-2 block">
              <span className="sr-only">Upload dataset</span>
              <input
                ref={fileRef}
                type="file"
                accept=".json,.csv,.tsv"
                onChange={onUpload}
                disabled={busy}
                className="block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-indigo-600 file:px-3 file:py-1.5 file:text-white hover:file:bg-indigo-500"
              />
            </label>
          </section>

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Loaded ({datasets.length})
            </h2>
            <div className="flex flex-col gap-1.5">
              {datasets.map((d) => (
                <button
                  key={d.name}
                  onClick={() => selectDataset(d.name)}
                  className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
                    selected === d.name
                      ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/15"
                      : "border-black/10 hover:bg-black/[.03] dark:border-white/10 dark:hover:bg-white/5"
                  }`}
                >
                  <div className="font-medium">{d.name}</div>
                  <div className="text-xs text-zinc-500">
                    {d.rows} rows · {d.column_count} cols
                  </div>
                </button>
              ))}
              {datasets.length === 0 && (
                <span className="text-xs text-zinc-400">
                  Load a sample to begin.
                </span>
              )}
            </div>
          </section>
        </aside>

        {/* Main */}
        <main className="flex min-w-0 flex-col gap-6">
          {!selected && !offline && (
            <div className="rounded-xl border border-dashed border-black/15 p-10 text-center text-sm text-zinc-500 dark:border-white/15">
              Select or load a dataset to explore it.
            </div>
          )}

          {breakdown && selected && (
            <>
              <Panel title={`Breakdown — ${breakdown.dataset}`}>
                <p className="mb-3 text-sm text-zinc-500">
                  {breakdown.rows} rows · {breakdown.columns.length} columns
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {breakdown.columns.map((c) => (
                    <span
                      key={c.name}
                      className="inline-flex items-center gap-1 rounded-md border border-black/10 px-2 py-1 text-xs dark:border-white/10"
                      title={`${c.dtype} · ${c.null_count} nulls · ${c.unique_count} unique`}
                    >
                      <KindDot kind={c.kind} />
                      {c.name}
                    </span>
                  ))}
                </div>
              </Panel>

              <Panel title="Playbooks">
                <div className="mb-2 flex flex-wrap gap-2">
                  {[
                    ["first_look", "First look"],
                    ["data_quality_audit", "Data quality audit"],
                    ["correlation_deep_dive", "Correlation deep dive"],
                  ].map(([pb, label]) => (
                    <button
                      key={pb}
                      onClick={() => runPlaybook(pb)}
                      disabled={busy}
                      className="rounded-lg border border-black/10 px-3 py-1.5 text-sm transition hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-indigo-500/10"
                    >
                      {label}
                    </button>
                  ))}
                  <div className="ml-auto flex gap-2">
                    <button
                      onClick={downloadReportPdf}
                      disabled={busy}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
                    >
                      ↓ PDF
                    </button>
                    <button
                      onClick={downloadReportMarkdown}
                      disabled={busy}
                      className="rounded-lg border border-black/15 px-3 py-1.5 text-sm hover:bg-black/[.03] disabled:opacity-50 dark:border-white/15 dark:hover:bg-white/5"
                    >
                      ↓ .md
                    </button>
                  </div>
                </div>
                {playbook && (
                  <div className="mt-3 flex flex-col gap-3">
                    <p className="text-sm text-zinc-500">{playbook.summary}</p>
                    {playbook.sections.map((sec, i) => (
                      <div key={i}>
                        <h3 className="mb-1 text-sm font-semibold">{sec.title}</h3>
                        <Markdown text={sec.body} />
                      </div>
                    ))}
                    {playbook.charts.map((spec, i) => (
                      <Chart key={i} spec={spec} />
                    ))}
                  </div>
                )}
              </Panel>

              {suggestions && suggestions.suggestions.length > 0 && (
                <Panel title="Suggested analysis">
                  <div className="flex flex-col gap-2">
                    {suggestions.suggestions.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => applySuggestion(s)}
                        disabled={busy}
                        className="rounded-lg border border-black/10 px-3 py-2 text-left transition hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-indigo-500/10"
                      >
                        <div className="text-sm font-medium">{s.title}</div>
                        <div className="text-xs text-zinc-500">{s.why}</div>
                      </button>
                    ))}
                  </div>
                </Panel>
              )}

              <Panel title="Correlations">
                <div className="mb-3 flex items-center gap-3 text-sm">
                  <label className="flex items-center gap-2">
                    threshold |r| ≥
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={threshold}
                      onChange={(e) => setThreshold(Number(e.target.value))}
                      className="w-20 rounded-md border border-black/15 px-2 py-1 dark:border-white/15 dark:bg-transparent"
                    />
                  </label>
                  <button
                    onClick={runCorrelations}
                    disabled={busy}
                    className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
                  >
                    Run
                  </button>
                </div>
                {correlations && (
                  <div className="flex flex-col gap-1.5">
                    {correlations.correlations.length === 0 && (
                      <span className="text-sm text-zinc-500">
                        No pairs at this threshold. Lower it and re-run.
                      </span>
                    )}
                    {correlations.correlations.map((c, i) => (
                      <button
                        key={i}
                        onClick={() =>
                          runChart({ chart_type: "scatter", x: c.x, y: c.y })
                        }
                        className="flex items-center justify-between rounded-lg border border-black/10 px-3 py-2 text-left text-sm transition hover:border-indigo-400 hover:bg-indigo-50 dark:border-white/10 dark:hover:bg-indigo-500/10"
                      >
                        <span>
                          {c.x} ↔ {c.y}
                        </span>
                        <span className="tabular-nums text-zinc-500">
                          r = {c.r} · {c.strength} {c.direction}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </Panel>

              {segment && (
                <Panel title={`Segment by ${segment.column}`}>
                  <div className="mb-3">
                    <button
                      onClick={() =>
                        runChart({ chart_type: "bar", x: segment.column })
                      }
                      className="rounded-md border border-black/15 px-2.5 py-1 text-xs hover:bg-black/[.03] dark:border-white/15 dark:hover:bg-white/5"
                    >
                      Chart counts
                    </button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-left text-xs uppercase text-zinc-500">
                        <tr>
                          <th className="py-1 pr-4">{segment.column}</th>
                          <th className="py-1 pr-4">count</th>
                          {segment.numeric_aggregates.map((n) => (
                            <th key={n} className="py-1 pr-4">
                              {n} (sum)
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {segment.segments.map((row, i) => (
                          <tr key={i} className="border-t border-black/5 dark:border-white/5">
                            <td className="py-1 pr-4">{String(row.value)}</td>
                            <td className="py-1 pr-4 tabular-nums">{row.count}</td>
                            {segment.numeric_aggregates.map((n) => (
                              <td key={n} className="py-1 pr-4 tabular-nums">
                                {fmt(row[`${n}_sum`])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              )}

              {chart && (
                <Panel title="Chart">
                  <Chart spec={chart} />
                </Panel>
              )}
            </>
          )}
        </main>

        {/* Chat rail */}
        <div className="xl:sticky xl:top-8 xl:h-[calc(100vh-4rem)] xl:w-[380px] xl:shrink-0">
          <div className="h-[600px] xl:h-full">
            <ChatPanel
              client={api}
              onActivity={onAgentActivity}
              title="Ask the data"
              placeholder="Ask about your data…"
              suggestions={[
                "Load the employee survey and tell me what drives satisfaction",
                "What's in the ecommerce orders data? Chart sales by region.",
                "Find the strongest correlations in product performance",
              ]}
              upload={{
                accept: ".json,.csv,.tsv",
                hint: "Drop a .json / .csv / .tsv file to analyze",
                upload: async (file) => {
                  const info = await api.upload(file);
                  return { name: info.name, detail: `${info.rows} rows` };
                },
                contextNote: (a) =>
                  `(I just uploaded the dataset "${a.name}" (${a.detail}) — it is loaded and ready to analyze.)`,
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-black/10 bg-white/50 p-5 dark:border-white/10 dark:bg-white/[.02]">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function KindDot({ kind }: { kind: string }) {
  const color =
    kind === "numerical"
      ? "bg-emerald-500"
      : kind === "datetime"
        ? "bg-sky-500"
        : kind === "boolean"
          ? "bg-amber-500"
          : "bg-zinc-400";
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} />;
}

function fmt(v: unknown): string {
  if (typeof v === "number")
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return v == null ? "—" : String(v);
}
