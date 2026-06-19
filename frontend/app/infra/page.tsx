"use client";

import { useCallback, useEffect, useState } from "react";

import { AgentChat } from "../components/AgentChat";
import { Markdown } from "../components/Markdown";
import { Rail } from "../components/Rail";
import {
  infra,
  WORKFLOWS,
  type LogsResult,
  type MonitorResult,
  type Service,
  type Snapshot,
} from "../lib/infra";

const ENVS = ["dev", "staging", "production"];

// Sensible default args per workflow (some prompts need a target).
function workflowArgs(id: string, env: string, worst?: string): [string, string] {
  switch (id) {
    case "infra-health-check":
      return [env, ""];
    case "deployment-strategy":
      return [worst || "payments", env];
    case "scaling-analysis":
      return ["compute", "auto"];
    case "incident-response":
      return ["service-degradation", "high"];
    case "security-audit":
      return ["full", ""];
    case "disaster-recovery":
      return ["region-outage", "4h"];
    default:
      return ["", ""];
  }
}

const statusColor = (s: string) =>
  s === "healthy" ? "var(--ok)" : s === "degraded" ? "var(--warn)" : "var(--crit)";

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

const panel: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  borderRadius: 16,
};

export default function InfraPage() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [mon, setMon] = useState<MonitorResult | null>(null);
  const [logs, setLogs] = useState<LogsResult | null>(null);
  const [env, setEnv] = useState("production");
  const [wf, setWf] = useState<{ id: string; arg: string; markdown: string } | null>(null);
  const [wfBusy, setWfBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, m, l] = await Promise.all([
      infra.fleet(),
      infra.monitor("all", "detailed"),
      infra.logs({ time_range: "1h", log_level: "ERROR" }),
    ]);
    setSnap(s);
    setMon(m);
    setLogs(l);
    return m;
  }, []);

  const runWorkflow = useCallback(
    async (id: string, worst?: string) => {
      setWfBusy(true);
      setError(null);
      try {
        const [arg, arg2] = workflowArgs(id, env, worst);
        const res = await infra.workflow(id, arg, arg2);
        setWf({ id, arg: arg || env, markdown: res.markdown });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setWfBusy(false);
      }
    },
    [env],
  );

  useEffect(() => {
    (async () => {
      try {
        await infra.health();
        const m = await refresh();
        const worst = m.services.find((s) => s.status !== "healthy")?.name;
        await runWorkflow("infra-health-check", worst);
      } catch {
        setOffline(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- derived (scoped to the active environment) ----
  const services: Service[] = (mon?.services ?? []).filter((s) => s.environment === env);
  const healthy = services.filter((s) => s.status === "healthy").length;
  const degraded = services.filter((s) => s.status === "degraded").length;
  const down = services.filter((s) => s.status === "down").length;
  const total = services.length;
  const cpuAvg = total ? Math.round(services.reduce((a, s) => a + s.cpu_percent, 0) / total) : 0;
  const score = total ? Math.round((healthy / total) * 100) : 100;
  const worst = [...services].filter((s) => s.status !== "healthy").sort((a, b) => b.cpu_percent - a.cpu_percent)[0];

  const lastBackup = [...(snap?.backups ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const dueSecret =
    snap?.secrets.find((s) => s.due) ??
    [...(snap?.secrets ?? [])].sort(
      (a, b) => b.age_days / b.rotation_interval_days - a.age_days / a.rotation_interval_days,
    )[0];
  const autoscale = snap?.resources.find((r) => r.auto_scaling);

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Rail />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* TOP BAR */}
        <div style={{ height: 60, flex: "none", borderBottom: "1px solid var(--line)", background: "var(--panel)", display: "flex", alignItems: "center", padding: "0 22px", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
            <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-.2px" }}>Infrastructure</span>
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>/ {env}</span>
          </div>
          <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
            <div style={{ display: "flex", border: "1px solid var(--line)", background: "var(--chip)", borderRadius: 10, padding: 3, gap: 2, fontSize: 12 }}>
              {ENVS.map((e) => (
                <button key={e} onClick={() => setEnv(e)} style={{ padding: "5px 14px", borderRadius: 7, border: "none", background: e === env ? "var(--accent)" : "transparent", color: e === env ? "var(--accent-ink)" : "var(--ink-3)", fontWeight: e === env ? 500 : 400 }}>
                  {e}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>us-east-1</div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--ink-2)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: offline ? "var(--crit)" : "var(--ok)", boxShadow: `0 0 0 3px color-mix(in srgb, ${offline ? "var(--crit)" : "var(--ok)"} 18%, transparent)` }} />
              {offline ? "Offline" : "Live"}
              <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>health {score}%</span>
            </div>
          </div>
        </div>

        {offline && (
          <div style={{ padding: "10px 26px", background: "color-mix(in srgb, var(--crit) 12%, var(--panel))", color: "var(--crit)", fontSize: 13 }}>
            Can&apos;t reach the Infra API. Start it with <span className="mono">uv run infra-api</span> in <span className="mono">infra/</span>.
          </div>
        )}

        {/* CONTENT ROW */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* SERVICES RAIL */}
          <div style={{ width: 268, flex: "none", borderRight: "1px solid var(--line)", background: "var(--panel)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "18px 18px 12px", display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>Services</span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)", background: "var(--chip)", borderRadius: 20, padding: "1px 8px" }}>{total}</span>
              {degraded + down > 0 && (
                <span style={{ marginLeft: "auto", fontSize: 11, color: down ? "var(--crit)" : "var(--warn)" }}>
                  {degraded + down} {down ? "critical" : "degraded"}
                </span>
              )}
            </div>
            <div style={{ padding: "0 14px", display: "flex", flexDirection: "column", gap: 7, overflowY: "auto" }}>
              {services.map((s) => {
                const crit = s.status === "down";
                return (
                  <div key={s.name} style={{ border: `1px solid ${crit ? "color-mix(in srgb, var(--crit) 34%, var(--line))" : "var(--line)"}`, background: crit ? "color-mix(in srgb, var(--crit) 9%, var(--panel))" : "transparent", borderRadius: 11, padding: "10px 12px", display: "flex", alignItems: "center", gap: 10, position: "relative", overflow: "hidden" }}>
                    {crit && <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "var(--crit)" }} />}
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor(s.status), flex: "none" }} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="mono" style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</div>
                      <div className="mono" style={{ fontSize: 10, color: s.status === "healthy" ? "var(--ink-3)" : statusColor(s.status) }}>
                        {s.replicas} inst · {Math.round(s.cpu_percent)}% cpu
                      </div>
                    </div>
                  </div>
                );
              })}
              {total === 0 && <div style={{ fontSize: 12, color: "var(--ink-3)", padding: "4px 2px" }}>No services in {env}.</div>}
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ margin: 14, border: "1px solid var(--line)", borderRadius: 12, padding: 13, background: "var(--panel-2)" }}>
              <div className="mono" style={{ fontSize: 10, letterSpacing: 1, color: "var(--ink-3)", marginBottom: 8 }}>TOOLS</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 11, color: "var(--ink-2)" }}>
                {["monitor", "deploy", "scale", "backup", "rotate", "logs"].map((t) => (
                  <span key={t} className="mono" style={{ border: "1px solid var(--line)", borderRadius: 6, padding: "3px 7px" }}>{t}</span>
                ))}
              </div>
            </div>
          </div>

          {/* MAIN CANVAS */}
          <div style={{ flex: 1, minWidth: 0, background: "var(--bg)", overflowY: "auto", padding: "24px 26px" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
              <div>
                <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-.5px" }}>{env}</div>
                <div className="mono" style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 3 }}>
                  {total} services · {healthy} healthy · {degraded + down} attention · checked just now
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button onClick={() => runWorkflow("deployment-strategy", worst?.name)} disabled={wfBusy} style={{ height: 34, padding: "0 14px", border: "1px solid var(--line)", background: "var(--panel)", borderRadius: 10, display: "flex", alignItems: "center", fontSize: 13, color: "var(--ink-2)" }}>
                  Deploy
                </button>
                <button onClick={() => runWorkflow("infra-health-check")} disabled={wfBusy} style={{ height: 34, padding: "0 16px", background: "var(--accent)", color: "var(--accent-ink)", border: "none", borderRadius: 10, display: "flex", alignItems: "center", fontSize: 13, fontWeight: 500 }}>
                  Health check
                </button>
              </div>
            </div>

            {/* metric tiles */}
            <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
              <div style={{ ...panel, padding: 16, display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ width: 58, height: 58, flex: "none", borderRadius: "50%", background: `conic-gradient(var(--ok) 0 ${score}%, var(--crit) ${score}% 100%)`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <div style={{ width: 44, height: 44, borderRadius: "50%", background: "var(--panel)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <span className="mono" style={{ fontSize: 15, fontWeight: 700 }}>{score}</span>
                  </div>
                </div>
                <div><div style={{ fontSize: 13, fontWeight: 600 }}>Health</div><div style={{ fontSize: 11, color: "var(--ink-3)" }}>score / 100</div></div>
              </div>
              <Tile value={`${healthy}`} suffix={`/${total}`} label="Services healthy" />
              <Tile value={`${cpuAvg}`} suffix="%" label="CPU avg" />
              <div style={{ ...panel, background: down ? "color-mix(in srgb, var(--crit) 8%, var(--panel))" : "var(--panel)", border: `1px solid ${down ? "color-mix(in srgb, var(--crit) 28%, var(--line))" : "var(--line)"}`, padding: 16 }}>
                <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: degraded + down ? "var(--crit)" : "var(--ink)" }}>{degraded + down}</div>
                <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{worst ? `Attention · ${worst.name}` : "All clear"}</div>
              </div>
            </div>

            {/* workflows */}
            <div style={{ ...panel, padding: "16px 18px", marginBottom: 18 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>Workflows</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 15 }}>
                {WORKFLOWS.map((w) => {
                  const active = wf?.id === w.id;
                  return (
                    <button key={w.id} onClick={() => runWorkflow(w.id, worst?.name)} disabled={wfBusy} style={{ height: 32, padding: "0 13px", border: `1px solid ${active ? "var(--accent)" : "var(--line)"}`, background: active ? "var(--accent-tint)" : "transparent", color: active ? "var(--accent)" : "var(--ink-2)", borderRadius: 20, display: "flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: active ? 500 : 400 }}>
                      {active && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)" }} />}
                      {w.label}
                    </button>
                  );
                })}
              </div>
              <div style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "15px 16px", background: "var(--panel-2)" }}>
                <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 11 }}>
                  /{wf?.id ?? "infra-health-check"} → {wf?.arg ?? env}
                </div>
                {wfBusy && !wf ? (
                  <div style={{ fontSize: 13, color: "var(--ink-3)" }}>Running…</div>
                ) : wf ? (
                  <Markdown text={wf.markdown} />
                ) : (
                  <div style={{ fontSize: 13, color: "var(--ink-3)" }}>Pick a workflow to run it against {env}.</div>
                )}
              </div>
            </div>

            {/* service monitor table */}
            <div style={{ ...panel, overflow: "hidden", marginBottom: 18 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 18px 12px" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
                  <span style={{ fontSize: 15, fontWeight: 600 }}>Service monitor</span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>monitor_services · threshold 80%</span>
                </div>
                <div className="mono" style={{ fontSize: 11, color: "var(--ink-2)", display: "flex", gap: 14 }}>
                  <Legend color="var(--ok)" label="ok" />
                  <Legend color="var(--warn)" label="warn" />
                  <Legend color="var(--crit)" label="critical" />
                </div>
              </div>
              <div className="mono" style={{ display: "grid", gridTemplateColumns: "1.5fr 0.9fr 1.4fr 1.4fr 0.8fr 0.9fr", gap: 14, padding: "8px 18px", fontSize: 10, letterSpacing: ".8px", color: "var(--ink-3)", borderBottom: "1px solid var(--line-2)" }}>
                <span>SERVICE</span><span>STATUS</span><span>CPU</span><span>MEM</span><span>INST</span><span>P95</span>
              </div>
              {services.map((s, i) => (
                <div key={s.name} style={{ display: "grid", gridTemplateColumns: "1.5fr 0.9fr 1.4fr 1.4fr 0.8fr 0.9fr", gap: 14, alignItems: "center", padding: "12px 18px", borderBottom: i < services.length - 1 ? "1px solid var(--line-2)" : "none", fontSize: 13 }}>
                  <span className="mono" style={{ fontSize: 12 }}>{s.name}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 7, color: s.status === "healthy" ? "var(--ink-2)" : statusColor(s.status), fontSize: 12 }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor(s.status) }} />
                    {s.status}
                  </span>
                  <Bar pct={s.cpu_percent} warn={80} />
                  <Bar pct={s.memory_percent} warn={88} soft />
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-2)" }}>{s.replicas}</span>
                  <span className="mono" style={{ fontSize: 12, color: s.latency_ms > 300 ? "var(--crit)" : "var(--ink-2)" }}>{Math.round(s.latency_ms)}ms</span>
                </div>
              ))}
            </div>

            {/* two-up: logs + ops */}
            <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 18 }}>
              <div style={{ ...panel, padding: "16px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                  <span style={{ fontSize: 15, fontWeight: 600 }}>Log analysis</span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>analyze_logs · 1h</span>
                </div>
                <div style={{ display: "flex", gap: 16, marginBottom: 14 }}>
                  <LogStat color="var(--crit)" n={logs?.by_level.ERROR ?? 0} label="ERROR" />
                  <LogStat color="var(--warn)" n={logs?.by_level.WARN ?? 0} label="WARN" />
                  <LogStat color="var(--ink-3)" n={logs?.by_level.INFO ?? 0} label="INFO" />
                </div>
                <div className="mono" style={{ fontSize: 11, lineHeight: 2, borderTop: "1px solid var(--line-2)", paddingTop: 10 }}>
                  {(logs?.samples ?? []).slice(0, 4).map((l, i) => (
                    <div key={i} style={{ display: "flex", gap: 10 }}>
                      <span style={{ color: l.level === "ERROR" || l.level === "FATAL" ? "var(--crit)" : "var(--warn)", width: 54 }}>{l.level}</span>
                      <span style={{ color: "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{l.message}</span>
                    </div>
                  ))}
                  {(logs?.samples?.length ?? 0) === 0 && <div style={{ color: "var(--ink-3)" }}>No matching log lines.</div>}
                </div>
              </div>
              <div style={{ ...panel, padding: "16px 18px" }}>
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Operations</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                  <OpRow color="var(--ok)" glyph="✓" title="Last backup" detail={lastBackup ? `${ago(lastBackup.created_at)} · ${lastBackup.verified ? "verified" : "unverified"} · ${lastBackup.backup_type}` : "none yet"} />
                  <OpRow color="var(--warn)" glyph="⟳" title="Secret rotation" detail={dueSecret ? (dueSecret.due ? `${dueSecret.name} overdue` : `${dueSecret.name} due in ${dueSecret.rotation_interval_days - dueSecret.age_days}d`) : "all current"} />
                  <OpRow color="var(--accent)" glyph="↑" title="Auto-scaling" detail={autoscale ? `${autoscale.kind} ${autoscale.capacity} ${autoscale.unit} · ${Math.round(autoscale.utilization)}%` : "off"} />
                </div>
              </div>
            </div>

            {error && <div style={{ marginTop: 16, color: "var(--crit)", fontSize: 12 }}>{error}</div>}
          </div>

          {/* CHAT */}
          <AgentChat
            client={infra}
            title="Infra agent"
            placeholder="Ask or run a workflow…"
            footer="6 workflows · 6 tools · destructive ops confirm first"
            contextChip={`context · ${env} · us-east-1`}
            onActivity={() => void refresh().catch(() => {})}
            suggestions={[
              "Run a health check on production",
              worst ? `Why is ${worst.name} degraded?` : "Summarize fleet health",
              "What secrets are overdue for rotation?",
            ]}
          />
        </div>
      </div>
    </div>
  );
}

function Tile({ value, suffix, label }: { value: string; suffix?: string; label: string }) {
  return (
    <div style={{ ...panel, padding: 16 }}>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>
        {value}
        {suffix && <span style={{ color: "var(--ink-3)", fontSize: 15 }}>{suffix}</span>}
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function Bar({ pct, warn, soft }: { pct: number; warn: number; soft?: boolean }) {
  const color = pct >= 88 ? "var(--crit)" : pct >= warn ? "var(--warn)" : soft ? "var(--accent-soft)" : "var(--ok)";
  const labelColor = pct >= warn ? color : "var(--ink-3)";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ flex: 1, height: 5, background: "var(--line)", borderRadius: 3, overflow: "hidden" }}>
        <span style={{ display: "block", width: `${Math.min(100, pct)}%`, height: "100%", background: color }} />
      </span>
      <span className="mono" style={{ fontSize: 11, color: labelColor }}>{Math.round(pct)}%</span>
    </span>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: color }} />
      {label}
    </span>
  );
}

function LogStat({ color, n, label }: { color: string; n: number; label: string }) {
  const display = n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13 }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
      <span className="mono" style={{ fontWeight: 700 }}>{display}</span>
      <span style={{ color: "var(--ink-3)" }}>{label}</span>
    </div>
  );
}

function OpRow({ color, glyph, title, detail }: { color: string; glyph: string; title: string; detail: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
      <div style={{ width: 30, height: 30, flex: "none", borderRadius: 8, background: `color-mix(in srgb, ${color} 16%, var(--panel))`, display: "flex", alignItems: "center", justifyContent: "center", color, fontSize: 13 }}>{glyph}</div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{title}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{detail}</div>
      </div>
    </div>
  );
}
