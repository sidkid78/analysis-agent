"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AgentChat } from "./components/AgentChat";
import { Markdown } from "./components/Markdown";
import { Rail } from "./components/Rail";
import {
  api,
  type Breakdown,
  type ColumnInfo,
  type CorrelationResult,
  type DatasetInfo,
  type Suggestions,
} from "./lib/api";

const KIND_COLOR: Record<string, string> = {
  numerical: "#16B981",
  datetime: "#0EA5E9",
  categorical: "#B6B1A6",
  boolean: "#E0962E",
};

function hashFloat(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = (h ^ s.charCodeAt(i)) * 16777619;
  return ((h >>> 0) % 1000) / 1000;
}
const spark = (name: string) => Array.from({ length: 6 }, (_, i) => 20 + hashFloat(`${name}:${i}`) * 75);

const panel: React.CSSProperties = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 16 };

export default function QuickData() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [samples, setSamples] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  const [correlations, setCorrelations] = useState<CorrelationResult | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestions | null>(null);
  const [result, setResult] = useState<{ title: string; markdown: string } | null>(null);
  const [filter, setFilter] = useState("");
  const [model, setModel] = useState("gemini-3.5-flash");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inject, setInject] = useState<{ text: string; nonce: number }>({ text: "", nonce: 0 });
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
    const res = await api.listDatasets().catch(() => null);
    if (res) setDatasets(res.datasets);
  }, []);

  const selectDataset = useCallback(
    async (name: string) => {
      setSelected(name);
      setCorrelations(null);
      setResult(null);
      const res = await run(async () => ({
        breakdown: await api.breakdown(name),
        suggestions: await api.suggestions(name),
        correlations: await api.correlations(name, 0.5).catch(() => null),
      }));
      if (res) {
        setBreakdown(res.breakdown);
        setSuggestions(res.suggestions);
        setCorrelations(res.correlations);
      }
    },
    [run],
  );

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        const [s, d, a] = await Promise.all([
          api.listSamples(),
          api.listDatasets(),
          api.agentStatus().catch(() => null),
        ]);
        setSamples(s.samples);
        setDatasets(d.datasets);
        if (a?.model) setModel(a.model);
        if (d.datasets[0]) selectDataset(d.datasets[0].name);
      } catch {
        setOffline(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  async function runPlaybook(pb: string, label: string) {
    if (!selected) return;
    const res = await run(() => api.playbook(selected, pb));
    if (res) {
      const body = [res.summary, ...res.sections.map((s) => `## ${s.title}\n${s.body}`)].join("\n\n");
      setResult({ title: label, markdown: body });
    }
  }

  async function runReport() {
    if (!selected) return;
    const res = await run(() => api.report(selected));
    if (res) setResult({ title: "Report", markdown: res.markdown });
  }

  async function exportPdf() {
    if (!selected) return;
    const blob = await run(() => api.reportPdf(selected));
    if (blob) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selected}-report.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  const cols = breakdown?.columns ?? [];
  const ds = datasets.find((d) => d.name === selected);
  const q = filter.trim().toLowerCase();
  const shownDatasets = q ? datasets.filter((d) => d.name.toLowerCase().includes(q)) : datasets;
  const shownSamples = q ? samples.filter((s) => s.toLowerCase().includes(q)) : samples;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* TOP BAR */}
        <div style={{ height: 60, flex: "none", borderBottom: "1px solid var(--line)", background: "var(--panel)", display: "flex", alignItems: "center", padding: "0 22px", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
            <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-.2px" }}>Quick Data</span>
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>/ {selected ?? "no dataset"}</span>
          </div>
          <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
            <div style={{ width: 430, maxWidth: "100%", height: 36, border: "1px solid var(--line)", background: "var(--chip)", borderRadius: 10, display: "flex", alignItems: "center", padding: "0 12px", gap: 10 }}>
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter datasets…"
                style={{ flex: 1, fontSize: 13, color: "var(--ink)", background: "transparent", border: "none", outline: "none" }}
              />
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--ink-2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: offline ? "var(--crit)" : "var(--ok)", boxShadow: `0 0 0 3px color-mix(in srgb, ${offline ? "var(--crit)" : "var(--ok)"} 18%, transparent)` }} />
              {offline ? "Offline" : "Connected"}
              <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>{api.base.replace(/^https?:\/\//, "")}</span>
            </div>
            <div style={{ width: 1, height: 20, background: "var(--line)" }} />
            <div className="mono" style={{ fontSize: 11, color: "var(--ink-2)", background: "var(--chip)", border: "1px solid var(--line)", borderRadius: 7, padding: "4px 9px" }}>{model}</div>
          </div>
        </div>

        {offline && (
          <div style={{ padding: "10px 26px", background: "color-mix(in srgb, var(--warn) 12%, var(--panel))", color: "var(--warn)", fontSize: 13 }}>
            Can&apos;t reach the backend. Start it with <span className="mono">uv run quickdata-api</span> in <span className="mono">backend/</span>.
          </div>
        )}

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* DATASETS PANEL */}
          <div style={{ width: 266, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "18px 18px 12px", display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>Datasets</span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)", background: "var(--chip)", borderRadius: 20, padding: "1px 8px" }}>{datasets.length}</span>
              <button onClick={() => fileRef.current?.click()} title="Upload" style={{ marginLeft: "auto", width: 30, height: 30, border: "1px solid var(--line)", background: "transparent", borderRadius: 9, color: "var(--ink-2)" }}>↑</button>
              <input ref={fileRef} type="file" accept=".json,.csv,.tsv" onChange={onUpload} style={{ display: "none" }} />
            </div>

            <div className="mono" style={{ padding: "4px 18px 8px", fontSize: 10, letterSpacing: 1, color: "var(--ink-3)" }}>LOADED</div>
            <div style={{ padding: "0 14px", display: "flex", flexDirection: "column", gap: 8, overflowY: "auto" }}>
              {shownDatasets.map((d) => {
                const sel = d.name === selected;
                return (
                  <button
                    key={d.name}
                    onClick={() => selectDataset(d.name)}
                    style={{
                      textAlign: "left",
                      border: `1px solid ${sel ? "var(--accent-soft)" : "var(--line)"}`,
                      background: sel ? "var(--accent-tint)" : "transparent",
                      borderRadius: 12,
                      padding: "12px 13px",
                      position: "relative",
                      overflow: "hidden",
                    }}
                  >
                    {sel && <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "var(--accent)" }} />}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ fontWeight: 600, color: sel ? "var(--ink)" : "var(--ink-2)" }}>{d.name}</span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{d.rows.toLocaleString()}×{d.column_count}</span>
                    </div>
                    <div style={{ display: "flex", height: 5, borderRadius: 3, overflow: "hidden", marginTop: 10, gap: 1.5, opacity: sel ? 1 : 0.65 }}>
                      {kindSegments(d.columns).map((s, i) => (
                        <div key={i} style={{ flex: s.n, background: s.color }} />
                      ))}
                    </div>
                  </button>
                );
              })}
              {datasets.length === 0 && <div style={{ fontSize: 12, color: "var(--ink-3)", padding: "2px 2px" }}>Load a sample to begin.</div>}
            </div>

            <div className="mono" style={{ padding: "18px 18px 8px", fontSize: 10, letterSpacing: 1, color: "var(--ink-3)" }}>SAMPLES</div>
            <div style={{ padding: "0 14px", display: "flex", flexDirection: "column", gap: 2, fontSize: 13, color: "var(--ink-2)", overflowY: "auto" }}>
              {shownSamples.map((s) => (
                <button key={s} onClick={() => loadSample(s)} disabled={busy} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 10px", borderRadius: 9, border: "none", background: "transparent", color: "var(--ink-2)", textAlign: "left" }}>
                  {s} <span style={{ color: "var(--ink-3)" }}>↓</span>
                </button>
              ))}
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ margin: 14, border: "1px dashed var(--line)", borderRadius: 12, padding: 14, textAlign: "center", fontSize: 12, color: "var(--ink-3)" }}>
              Upload a <span className="mono">.csv / .json / .tsv</span>
            </div>
          </div>

          {/* MAIN CANVAS */}
          <div style={{ flex: 1, minWidth: 0, background: "var(--bg)", overflowY: "auto", padding: "24px 26px" }}>
            {!selected && !offline && (
              <div style={{ border: "1px dashed var(--line)", borderRadius: 12, padding: 40, textAlign: "center", fontSize: 13, color: "var(--ink-3)" }}>
                Select or load a dataset to explore it.
              </div>
            )}

            {selected && breakdown && (
              <>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 14 }}>
                  <div>
                    <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-.5px" }}>{selected}</div>
                    <div className="mono" style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 3 }}>
                      {breakdown.rows.toLocaleString()} rows · {cols.length} columns{ds?.source ? ` · ${ds.source.split(/[\\/]/).pop()}` : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <button onClick={exportPdf} disabled={busy} style={{ height: 34, padding: "0 14px", border: "1px solid var(--line)", background: "var(--panel)", borderRadius: 10, display: "flex", alignItems: "center", gap: 7, fontSize: 13, color: "var(--ink-2)" }}>
                      Export <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>PDF</span>
                    </button>
                    <button onClick={runReport} disabled={busy} style={{ height: 34, padding: "0 16px", background: "var(--accent)", color: "var(--accent-ink)", border: "none", borderRadius: 10, display: "flex", alignItems: "center", fontSize: 13, fontWeight: 500 }}>
                      Run report
                    </button>
                  </div>
                </div>

                {/* playbooks */}
                <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
                  {[
                    ["first_look", "First look"],
                    ["data_quality_audit", "Data quality audit"],
                    ["correlation_deep_dive", "Correlation deep dive"],
                  ].map(([pb, label], i) => (
                    <button key={pb} onClick={() => runPlaybook(pb, label)} disabled={busy} style={{ height: 32, padding: "0 13px", border: "1px solid var(--line)", background: "var(--panel)", borderRadius: 20, display: "flex", alignItems: "center", gap: 7, fontSize: 13, color: i === 0 ? "var(--ink)" : "var(--ink-2)" }}>
                      {i === 0 && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)" }} />}
                      {label}
                    </button>
                  ))}
                </div>

                {result && (
                  <div style={{ ...panel, padding: "15px 18px", marginBottom: 18 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                      <span style={{ fontSize: 14, fontWeight: 600 }}>{result.title}</span>
                      <button onClick={() => setResult(null)} style={{ fontSize: 11, color: "var(--ink-3)", border: "1px solid var(--line)", background: "transparent", borderRadius: 7, padding: "3px 8px" }}>Close</button>
                    </div>
                    <Markdown text={result.markdown} />
                  </div>
                )}

                {/* schema */}
                <div style={{ ...panel, overflow: "hidden", marginBottom: 18 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 18px 12px" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
                      <span style={{ fontSize: 15, fontWeight: 600 }}>Schema</span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{cols.length} columns</span>
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-2)", display: "flex", gap: 14 }}>
                      <KindLegend kind="numerical" label="numeric" />
                      <KindLegend kind="datetime" label="date" />
                      <KindLegend kind="categorical" label="categorical" />
                      <KindLegend kind="boolean" label="boolean" />
                    </div>
                  </div>
                  <div className="mono" style={{ display: "grid", gridTemplateColumns: "1.6fr 1.1fr 1.3fr 0.9fr 1.6fr", gap: 14, padding: "8px 18px", fontSize: 10, letterSpacing: ".8px", color: "var(--ink-3)", borderBottom: "1px solid var(--line-2)" }}>
                    <span>COLUMN</span><span>TYPE</span><span>NULLS</span><span>UNIQUE</span><span>DISTRIBUTION</span>
                  </div>
                  {cols.map((c, i) => {
                    const nullPct = breakdown.rows ? (c.null_count / breakdown.rows) * 100 : 0;
                    return (
                      <div key={c.name} style={{ display: "grid", gridTemplateColumns: "1.6fr 1.1fr 1.3fr 0.9fr 1.6fr", gap: 14, alignItems: "center", padding: "13px 18px", borderBottom: i < cols.length - 1 ? "1px solid var(--line-2)" : "none", fontSize: 13 }}>
                        <span style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.name}</span>
                        <span style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--ink-2)" }}>
                          <span style={{ width: 7, height: 7, borderRadius: "50%", background: KIND_COLOR[c.kind] }} />{c.kind}
                        </span>
                        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ flex: 1, height: 5, background: "var(--line)", borderRadius: 3, overflow: "hidden" }}>
                            <span style={{ display: "block", width: `${Math.min(100, nullPct)}%`, height: "100%", background: nullPct > 20 ? "var(--warn)" : "var(--ink-3)" }} />
                          </span>
                          <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{nullPct.toFixed(0)}%</span>
                        </span>
                        <span className="mono" style={{ color: "var(--ink-2)" }}>{c.unique_count.toLocaleString()}</span>
                        <span style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 22 }}>
                          {spark(c.name).map((h, hi) => (
                            <span key={hi} style={{ flex: 1, background: "var(--accent-soft)", height: `${h}%` }} />
                          ))}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* two-up */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
                  <div style={{ ...panel, padding: "16px 18px" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                      <span style={{ fontSize: 15, fontWeight: 600 }}>Correlations</span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)", border: "1px solid var(--line)", borderRadius: 7, padding: "3px 8px" }}>|r| ≥ 0.5</span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
                      {(correlations?.correlations ?? []).slice(0, 5).map((c, i) => (
                        <div key={i}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 5 }}>
                            <span>{c.x} ↔ {c.y}</span>
                            <span className="mono" style={{ color: "var(--ink-2)" }}>{c.r.toFixed(2)}</span>
                          </div>
                          <div style={{ height: 6, background: "var(--line)", borderRadius: 4, overflow: "hidden" }}>
                            <div style={{ width: `${Math.min(100, Math.abs(c.r) * 100)}%`, height: "100%", background: c.direction === "negative" ? "#C2452E" : "var(--accent)", borderRadius: 4 }} />
                          </div>
                        </div>
                      ))}
                      {(correlations?.correlations?.length ?? 0) === 0 && <div style={{ fontSize: 13, color: "var(--ink-3)" }}>No correlations at |r| ≥ 0.5.</div>}
                    </div>
                  </div>

                  <div style={{ ...panel, padding: "16px 18px" }}>
                    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Suggested next</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                      {(suggestions?.suggestions ?? []).map((s, i) => (
                        <button key={i} onClick={() => setInject({ text: s.title, nonce: inject.nonce + 1 })} style={{ display: "flex", alignItems: "center", gap: 11, padding: "11px 12px", border: "1px solid var(--line)", borderRadius: 11, background: "transparent", textAlign: "left" }}>
                          <div style={{ width: 30, height: 30, flex: "none", borderRadius: 8, background: "var(--accent-tint)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent)", fontSize: 13 }}>
                            {s.operation === "segment" ? "▤" : s.operation === "correlations" ? "◈" : "⌗"}
                          </div>
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 500 }}>{s.title}</div>
                            <div style={{ fontSize: 11, color: "var(--ink-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.why}</div>
                          </div>
                          <span style={{ marginLeft: "auto", color: "var(--ink-3)" }}>→</span>
                        </button>
                      ))}
                      {(suggestions?.suggestions?.length ?? 0) === 0 && <div style={{ fontSize: 13, color: "var(--ink-3)" }}>No suggestions.</div>}
                    </div>
                  </div>
                </div>

                {error && <div style={{ marginTop: 16, color: "var(--crit)", fontSize: 12 }}>{error}</div>}
              </>
            )}
          </div>

          {/* CHAT */}
          <AgentChat
            client={api}
            title="Assistant"
            placeholder="Ask about your data…"
            footer="Shares the backend store · charts render inline"
            showCharts
            onActivity={refreshDatasets}
            inject={inject}
            suggestions={[
              "What's in this dataset? Chart the most interesting breakdown.",
              "Find the strongest correlations and explain them.",
              "Profile data quality and suggest fixes.",
            ]}
          />
        </div>
      </div>
    </div>
  );
}

function kindSegments(columns: ColumnInfo[]): { n: number; color: string }[] {
  const counts: Record<string, number> = {};
  for (const c of columns) counts[c.kind] = (counts[c.kind] ?? 0) + 1;
  return (["numerical", "datetime", "categorical", "boolean"] as const)
    .map((k) => ({ n: counts[k] ?? 0, color: KIND_COLOR[k] }))
    .filter((s) => s.n > 0);
}

function KindLegend({ kind, label }: { kind: string; label: string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: KIND_COLOR[kind] }} />
      {label}
    </span>
  );
}
