"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChartSpec } from "../lib/api";
import {
  smartdev,
  WORKFLOWS,
  type Analysis,
  type WorkflowResult,
} from "../lib/smartdev";
import { Chart } from "../components/Chart";
import { ChatPanel } from "../components/ChatPanel";
import { Markdown } from "../components/Markdown";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "text-red-600",
  high: "text-red-500",
  warning: "text-amber-600",
  info: "text-zinc-500",
};

export default function DevPage() {
  const [path, setPath] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowResult | null>(null);
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

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
    const res = await run(() => smartdev.analyze(path.trim()));
    if (res) setAnalysis(res);
  }

  async function runWorkflow(id: string) {
    if (!path.trim()) {
      setError("Enter a project path first.");
      return;
    }
    const res = await run(() =>
      smartdev.workflow(id, { project_path: path.trim(), issue: detail, target: detail }),
    );
    if (res) setWorkflow(res);
  }

  const issuesChart: ChartSpec | null = analysis
    ? {
        dataset: analysis.root,
        type: "bar",
        subtype: null,
        title: "Issues by kind",
        x_label: "kind",
        y_label: "count",
        data: Object.entries(analysis.issue_counts).map(([label, value]) => ({ label, value })),
      }
    : null;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-[88rem] flex-col gap-6 px-6 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Smart Dev</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Point at a project to analyze it, run a workflow, or ask the dev agent.
          </p>
        </div>
        <span className="flex items-center gap-2 text-xs text-zinc-500">
          <span className={`inline-block h-2 w-2 rounded-full ${offline ? "bg-red-500" : "bg-emerald-500"}`} />
          {offline ? "API offline" : "API connected"} · {smartdev.base}
        </span>
      </header>

      {offline && (
        <div className="rounded-lg border border-amber-300/50 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          Can&apos;t reach the Smart Dev API. Start it with{" "}
          <code className="rounded bg-black/10 px-1 dark:bg-white/10">uv run smart-dev-api</code> in{" "}
          <code>smart-dev/</code>.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && analyze()}
          placeholder="Absolute project path, e.g. C:/Users/you/repo"
          className="min-w-0 flex-1 rounded-lg border border-black/15 px-3 py-2 text-sm outline-none focus:border-indigo-400 dark:border-white/15 dark:bg-transparent"
        />
        <button
          onClick={analyze}
          disabled={busy || !path.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          Analyze
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-300/50 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
        <main className="flex min-w-0 flex-col gap-6">
          {!analysis && !offline && (
            <div className="rounded-xl border border-dashed border-black/15 p-10 text-center text-sm text-zinc-500 dark:border-white/15">
              Enter a project path and Analyze, or just ask the agent on the right.
            </div>
          )}

          {analysis && (
            <>
              <Panel title={`Analysis — ${shorten(analysis.root)}`}>
                <div className="mb-3 flex flex-wrap gap-4 text-sm">
                  <Metric label="Quality" value={`${analysis.metrics.quality_score}/100`} />
                  <Metric label="Files" value={analysis.files_analyzed} />
                  <Metric label="Lines" value={analysis.total_lines.toLocaleString()} />
                  <Metric label="Avg complexity" value={analysis.metrics.avg_function_complexity} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(analysis.languages).map(([lang, n]) => (
                    <span key={lang} className="rounded-md border border-black/10 px-2 py-1 text-xs dark:border-white/10">
                      {lang} · {n}
                    </span>
                  ))}
                </div>
                {analysis.recommendations.length > 0 && (
                  <ul className="mt-3 list-disc space-y-0.5 pl-5 text-sm text-zinc-600 dark:text-zinc-300">
                    {analysis.recommendations.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
              </Panel>

              {analysis.security_findings.length > 0 && (
                <Panel title={`🔴 Security findings (${analysis.security_findings.length})`}>
                  <ul className="flex flex-col gap-1 text-sm">
                    {analysis.security_findings.map((s, i) => (
                      <li key={i} className="font-mono text-xs">
                        <span className="text-red-600">{rel(s.file, analysis.root)}:{s.line}</span> — {s.message}
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}

              <Panel title="Workflows">
                <div className="mb-3 flex flex-wrap gap-2">
                  {WORKFLOWS.map((w) => (
                    <button
                      key={w.id}
                      onClick={() => runWorkflow(w.id)}
                      disabled={busy}
                      className="rounded-lg border border-black/10 px-3 py-1.5 text-sm transition hover:border-indigo-400 hover:bg-indigo-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-indigo-500/10"
                    >
                      {w.label}
                    </button>
                  ))}
                </div>
                <input
                  value={detail}
                  onChange={(e) => setDetail(e.target.value)}
                  placeholder="Issue (for Debug) or target module (for Refactor)"
                  className="w-full rounded-lg border border-black/15 px-3 py-1.5 text-xs outline-none focus:border-indigo-400 dark:border-white/15 dark:bg-transparent"
                />
                {workflow && (
                  <div className="mt-4 rounded-lg border border-black/10 p-4 dark:border-white/10">
                    <Markdown text={workflow.markdown} />
                  </div>
                )}
              </Panel>

              {issuesChart && issuesChart.data.length > 0 && (
                <Panel title="Issues by kind">
                  <Chart spec={issuesChart} />
                </Panel>
              )}

              {analysis.issues.length > 0 && (
                <Panel title={`Findings (${analysis.issues.length})`}>
                  <div className="flex flex-col gap-1 text-sm">
                    {analysis.issues.map((iss, i) => (
                      <div key={i} className="font-mono text-xs">
                        <span className={SEVERITY_COLOR[iss.severity] ?? "text-zinc-500"}>{iss.severity}</span>{" "}
                        <span className="text-zinc-500">{rel(iss.file, analysis.root)}:{iss.line}</span> —{" "}
                        {iss.kind}: {iss.message}
                      </div>
                    ))}
                  </div>
                </Panel>
              )}
            </>
          )}
        </main>

        <div className="xl:sticky xl:top-8 xl:h-[calc(100vh-7rem)] xl:shrink-0">
          <div className="h-[600px] xl:h-full">
            <ChatPanel
              client={smartdev}
              title="Ask Smart Dev"
              placeholder="Ask about this project…"
              contextLine={path.trim() ? `Project: ${path.trim()}` : null}
              suggestions={[
                "Review this project and tell me the most urgent problem",
                "Are there any security issues or hardcoded secrets?",
                "What are the most complex files and how would you refactor them?",
              ]}
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

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-zinc-500">{label}</div>
    </div>
  );
}

function rel(file: string, root: string): string {
  return file.startsWith(root) ? file.slice(root.length).replace(/^[\\/]/, "") : file;
}

function shorten(p: string): string {
  const parts = p.replace(/[\\/]+$/, "").split(/[\\/]/);
  return parts.slice(-2).join("/");
}
