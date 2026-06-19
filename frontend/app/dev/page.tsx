"use client";

import { useCallback, useEffect, useState } from "react";

import { AgentChat } from "../components/AgentChat";
import { Markdown } from "../components/Markdown";
import { Rail } from "../components/Rail";
import { smartdev, WORKFLOWS, type Analysis, type WorkflowResult } from "../lib/smartdev";

const SEV_COLOR: Record<string, string> = {
  critical: "var(--crit)",
  high: "#FB7185",
  warning: "var(--warn)",
  info: "var(--ink-3)",
};

const panel: React.CSSProperties = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 16 };

function rel(file: string, root: string): string {
  return file.startsWith(root) ? file.slice(root.length).replace(/^[\\/]/, "") : file;
}
function shorten(p: string): string {
  const parts = p.replace(/[\\/]+$/, "").split(/[\\/]/);
  return parts.slice(-2).join("/") || p;
}

export default function SmartDev() {
  const [path, setPath] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowResult | null>(null);
  const [activeWf, setActiveWf] = useState<string | null>(null);
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    smartdev.health().catch(() => setOffline(true));
  }, []);

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

  async function analyze() {
    if (!path.trim()) return;
    setWorkflow(null);
    setActiveWf(null);
    const res = await run(() => smartdev.analyze(path.trim()));
    if (res) setAnalysis(res);
  }

  async function runWorkflow(id: string) {
    if (!path.trim()) {
      setError("Enter a project path first.");
      return;
    }
    setActiveWf(id);
    const res = await run(() => smartdev.workflow(id, { project_path: path.trim(), issue: detail, target: detail }));
    if (res) setWorkflow(res);
  }

  const m = analysis?.metrics;
  const score = m?.quality_score ?? 0;
  const hotspots = m?.complexity_hotspots ?? [];
  const maxHot = Math.max(1, ...hotspots.map((h) => h.max_complexity));
  const counts = analysis?.issue_counts ?? {};
  const scans = {
    secrets: analysis?.security_findings.length ?? 0,
    debug: counts["debug"] ?? 0,
    todo: counts["todo"] ?? 0,
  };
  const langs = Object.entries(analysis?.languages ?? {}).sort((a, b) => b[1] - a[1]);
  const maxKind = Math.max(1, ...Object.values(counts));

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* TOP BAR */}
        <div style={{ height: 60, flex: "none", borderBottom: "1px solid var(--line)", background: "var(--panel)", display: "flex", alignItems: "center", padding: "0 22px", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
            <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-.2px" }}>Smart Dev</span>
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>/ {analysis ? shorten(analysis.root) : "no project"}</span>
          </div>
          <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
            <div style={{ width: 520, maxWidth: "100%", height: 36, border: "1px solid var(--line)", background: "var(--chip)", borderRadius: 10, display: "flex", alignItems: "center", padding: "0 6px 0 12px", gap: 10 }}>
              <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>PATH</span>
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && analyze()}
                placeholder="C:/Users/you/repo"
                className="mono"
                style={{ flex: 1, fontSize: 12, color: "var(--ink)", background: "transparent", border: "none", outline: "none" }}
              />
              <button onClick={analyze} disabled={busy || !path.trim()} style={{ height: 26, padding: "0 14px", background: "var(--accent)", color: "var(--accent-ink)", border: "none", borderRadius: 7, fontSize: 12, fontWeight: 500 }}>
                Analyze
              </button>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--ink-2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: offline ? "var(--crit)" : "var(--ok)", boxShadow: `0 0 0 3px color-mix(in srgb, ${offline ? "var(--crit)" : "var(--ok)"} 18%, transparent)` }} />
              {offline ? "Offline" : "Connected"}
              <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>{smartdev.base.replace(/^https?:\/\//, "")}</span>
            </div>
            <div style={{ width: 1, height: 20, background: "var(--line)" }} />
            <div className="mono" style={{ fontSize: 11, color: "var(--ink-2)", background: "var(--chip)", border: "1px solid var(--line)", borderRadius: 7, padding: "4px 9px" }}>stateless</div>
          </div>
        </div>

        {error && (
          <div style={{ padding: "10px 26px", background: "color-mix(in srgb, var(--crit) 12%, var(--panel))", color: "var(--crit)", fontSize: 13 }}>{error}</div>
        )}

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* HOTSPOTS RAIL */}
          <div style={{ width: 268, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "18px 18px 12px", display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>Hotspots</span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)", background: "var(--chip)", borderRadius: 20, padding: "1px 8px" }}>{hotspots.length}</span>
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--ink-3)" }}>by complexity</span>
            </div>
            <div style={{ padding: "0 14px", display: "flex", flexDirection: "column", gap: 7, overflowY: "auto" }}>
              {hotspots.map((h, i) => {
                const flagged = i === 0;
                return (
                  <div key={h.path} style={{ border: `1px solid ${flagged ? "var(--accent-soft)" : "var(--line)"}`, background: flagged ? "var(--accent-tint)" : "transparent", borderRadius: 11, padding: "11px 12px", position: "relative", overflow: "hidden" }}>
                    {flagged && <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "var(--accent)" }} />}
                    <div className="mono" style={{ fontSize: 12, marginBottom: 7, color: flagged ? "var(--ink)" : "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{rel(h.path, analysis?.root ?? "")}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ flex: 1, height: 5, background: "var(--line)", borderRadius: 3, overflow: "hidden" }}>
                        <span style={{ display: "block", width: `${(h.max_complexity / maxHot) * 100}%`, height: "100%", background: flagged ? "var(--accent)" : "var(--accent-soft)" }} />
                      </span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{h.max_complexity}</span>
                    </div>
                    <div className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 6 }}>{h.language} · {h.lines} ln{h.issues ? ` · ${h.issues} issue${h.issues > 1 ? "s" : ""}` : ""}</div>
                  </div>
                );
              })}
              {!analysis && <div style={{ fontSize: 12, color: "var(--ink-3)", padding: "2px" }}>Analyze a project to see hotspots.</div>}
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ margin: 14, border: "1px solid var(--line)", borderRadius: 12, padding: 13, background: "var(--panel-2)" }}>
              <div className="mono" style={{ fontSize: 10, letterSpacing: 1, color: "var(--ink-3)", marginBottom: 8 }}>SCANS</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7, fontSize: 12, color: "var(--ink-2)" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>Secrets <span className="mono" style={{ color: scans.secrets ? "var(--crit)" : "var(--ink-3)" }}>{scans.secrets}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>Debug stmts <span className="mono" style={{ color: scans.debug ? "var(--warn)" : "var(--ink-3)" }}>{scans.debug}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>TODOs <span className="mono" style={{ color: "var(--ink-3)" }}>{scans.todo}</span></div>
              </div>
            </div>
          </div>

          {/* MAIN */}
          <div style={{ flex: 1, minWidth: 0, background: "var(--bg)", overflowY: "auto", padding: "24px 26px" }}>
            {!analysis && !offline && (
              <div style={{ border: "1px dashed var(--line)", borderRadius: 12, padding: 40, textAlign: "center", fontSize: 13, color: "var(--ink-3)" }}>
                Enter an absolute project path above and Analyze — or just ask the agent on the right.
              </div>
            )}

            {analysis && m && (
              <>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
                  <div>
                    <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-.5px" }}>{shorten(analysis.root)}</div>
                    <div className="mono" style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 3 }}>
                      {analysis.files_analyzed} files · {analysis.total_lines.toLocaleString()} lines · analyzed just now
                    </div>
                  </div>
                  <button onClick={analyze} disabled={busy} style={{ height: 34, padding: "0 14px", border: "1px solid var(--line)", background: "var(--panel)", borderRadius: 10, fontSize: 13, color: "var(--ink-2)" }}>Re-analyze</button>
                </div>

                {/* metric tiles */}
                <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
                  <div style={{ ...panel, padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{ width: 58, height: 58, flex: "none", borderRadius: "50%", background: `conic-gradient(var(--accent) 0 ${score}%, var(--line) ${score}% 100%)`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--panel)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <span className="mono" style={{ fontSize: 15, fontWeight: 700 }}>{score}</span>
                      </div>
                    </div>
                    <div><div style={{ fontSize: 13, fontWeight: 600 }}>Quality</div><div style={{ fontSize: 11, color: "var(--ink-3)" }}>score / 100</div></div>
                  </div>
                  <Tile value={analysis.files_analyzed.toLocaleString()} label="Files" />
                  <Tile value={analysis.total_lines.toLocaleString()} label="Lines" />
                  <Tile value={`${m.avg_function_complexity}`} label="Avg complexity" />
                </div>

                {/* languages + recs */}
                <div style={{ ...panel, padding: "16px 18px", marginBottom: 18 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
                    <span style={{ fontSize: 15, fontWeight: 600 }}>Languages</span>
                    <div style={{ flex: 1, display: "flex", height: 7, borderRadius: 4, overflow: "hidden", gap: 2 }}>
                      {langs.map(([l, n], i) => (
                        <div key={l} style={{ flex: n, background: i === 0 ? "var(--accent)" : "var(--accent-soft)" }} />
                      ))}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 12, marginBottom: analysis.recommendations.length ? 14 : 0 }}>
                    {langs.map(([l, n], i) => (
                      <span key={l} className="mono" style={{ border: "1px solid var(--line)", borderRadius: 7, padding: "4px 10px", color: i === 0 ? "var(--ink)" : "var(--ink-2)" }}>
                        {i === 0 && <span style={{ color: "var(--accent)" }}>● </span>}{l} · {n}
                      </span>
                    ))}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {analysis.recommendations.slice(0, 4).map((r, i) => (
                      <div key={i} style={{ display: "flex", gap: 9, fontSize: 13, color: "var(--ink-2)" }}>
                        <span style={{ color: "var(--accent)" }}>→</span> {r}
                      </div>
                    ))}
                  </div>
                </div>

                {/* security */}
                {analysis.security_findings.length > 0 && (
                  <div style={{ background: "color-mix(in srgb, var(--crit) 9%, var(--panel))", border: "1px solid color-mix(in srgb, var(--crit) 32%, var(--line))", borderRadius: 16, padding: "16px 18px", marginBottom: 18 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 12 }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--crit)" }} />
                      <span style={{ fontSize: 15, fontWeight: 600 }}>Security findings</span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--crit)", background: "color-mix(in srgb, var(--crit) 16%, transparent)", borderRadius: 20, padding: "1px 8px" }}>{analysis.security_findings.length}</span>
                    </div>
                    <div className="mono" style={{ fontSize: 12, lineHeight: 2.1 }}>
                      {analysis.security_findings.slice(0, 6).map((s, i) => (
                        <div key={i} style={{ display: "flex", gap: 10 }}>
                          <span style={{ color: "var(--crit)", width: 180, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{rel(s.file, analysis.root)}:{s.line}</span>
                          <span style={{ color: "var(--ink-2)" }}>{s.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* workflows */}
                <div style={{ ...panel, padding: "16px 18px", marginBottom: 18 }}>
                  <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>Workflows</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                    {WORKFLOWS.map((w) => {
                      const active = activeWf === w.id;
                      return (
                        <button key={w.id} onClick={() => runWorkflow(w.id)} disabled={busy} style={{ height: 32, padding: "0 13px", border: `1px solid ${active ? "var(--accent)" : "var(--line)"}`, background: active ? "var(--accent-tint)" : "transparent", color: active ? "var(--accent)" : "var(--ink-2)", borderRadius: 20, display: "flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: active ? 500 : 400 }}>
                          {active && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)" }} />}
                          {w.label}
                        </button>
                      );
                    })}
                  </div>
                  <input
                    value={detail}
                    onChange={(e) => setDetail(e.target.value)}
                    placeholder="Issue (for Debug) or target module (for Refactor)…"
                    style={{ width: "100%", height: 34, border: "1px solid var(--line)", background: "var(--panel-2)", borderRadius: 9, padding: "0 12px", fontSize: 12, color: "var(--ink)", outline: "none", marginBottom: workflow ? 12 : 0 }}
                  />
                  {workflow && (
                    <div style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "15px 16px", background: "var(--panel-2)" }}>
                      <Markdown text={workflow.markdown} />
                    </div>
                  )}
                </div>

                {/* findings + issues chart */}
                <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 18 }}>
                  <div style={{ ...panel, padding: "16px 18px" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 9, marginBottom: 12 }}>
                      <span style={{ fontSize: 15, fontWeight: 600 }}>Findings</span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{analysis.issues.length}</span>
                    </div>
                    <div className="mono" style={{ fontSize: 12, lineHeight: 2.2 }}>
                      {analysis.issues.slice(0, 6).map((iss, i) => (
                        <div key={i} style={{ display: "flex", gap: 10 }}>
                          <span style={{ color: SEV_COLOR[iss.severity] ?? "var(--ink-3)", width: 62 }}>{iss.severity}</span>
                          <span style={{ color: "var(--ink-3)", width: 120, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{rel(iss.file, analysis.root)}:{iss.line}</span>
                          <span style={{ color: "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{iss.kind}</span>
                        </div>
                      ))}
                      {analysis.issues.length === 0 && <div style={{ color: "var(--ink-3)" }}>No issues found.</div>}
                    </div>
                  </div>
                  <div style={{ ...panel, padding: "16px 18px" }}>
                    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Issues by kind</div>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: 12, height: 96, borderBottom: "1px solid var(--line)" }}>
                      {Object.entries(counts).slice(0, 5).map(([k, n], i) => (
                        <div key={k} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%", gap: 5 }}>
                          <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>{n}</span>
                          <div style={{ width: "100%", height: `${(n / maxKind) * 90}%`, background: i === 0 ? "var(--accent)" : "var(--accent-soft)", borderRadius: "4px 4px 0 0" }} />
                        </div>
                      ))}
                    </div>
                    <div className="mono" style={{ display: "flex", gap: 12, fontSize: 9, color: "var(--ink-3)", marginTop: 6 }}>
                      {Object.keys(counts).slice(0, 5).map((k) => (
                        <span key={k} style={{ flex: 1, textAlign: "center", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{k}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* CHAT */}
          <AgentChat
            client={smartdev}
            title="Smart Dev"
            placeholder="Ask about this project…"
            footer="Stateless · path-scoped · no charts"
            contextChip={path.trim() ? `📁 ${shorten(path.trim())}` : undefined}
            contextPrefix={() => (path.trim() ? `(Project: ${path.trim()})` : null)}
            suggestions={[
              "Review this project and tell me the most urgent problem",
              "Are there any security issues or hardcoded secrets?",
              "Which files are most complex and how would you refactor them?",
            ]}
          />
        </div>
      </div>
    </div>
  );
}

function Tile({ value, label }: { value: string; label: string }) {
  return (
    <div style={{ ...panel, padding: 16 }}>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{label}</div>
    </div>
  );
}
