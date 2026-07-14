// Client for the Smart Dev FastAPI backend (the "Dev" section).

import { streamChat, type AgentStatus, type ChatClient } from "./chat";

const BASE =
  process.env.NEXT_PUBLIC_SMARTDEV_API_BASE ?? "http://localhost:8030";

export interface CodeIssue {
  file: string;
  line: number;
  severity: string;
  kind: string;
  message: string;
}

export interface Hotspot {
  path: string;
  language: string;
  lines: number;
  max_complexity: number;
  issues: number;
}

export interface Scope {
  mode: string;
  base?: string;
  files?: number;
  error?: string;
}

export interface Analysis {
  root: string;
  scope?: Scope;
  message?: string;
  files_analyzed: number;
  files_truncated: boolean;
  languages: Record<string, number>;
  total_lines: number;
  metrics: {
    avg_function_complexity: number;
    quality_score: number;
    complexity_hotspots: Hotspot[];
  };
  issue_counts: Record<string, number>;
  issues: CodeIssue[];
  security_findings: CodeIssue[];
  recommendations: string[];
}

export interface WorkflowResult {
  workflow: string;
  markdown: string;
}

export interface LintFinding {
  tool: string;
  file: string;
  line: number | null;
  column: number | null;
  code: string | null;
  severity: string;
  message: string;
  fixable?: boolean;
}

export interface LinterRun {
  tool: string;
  status: string;
  found?: number;
  returned?: number;
  fixable?: number;
  note?: string;
}

export interface LintResult {
  project: string;
  scope?: Scope;
  linters: LinterRun[];
  finding_count?: number;
  by_severity?: Record<string, number>;
  findings?: LintFinding[];
  summary?: string;
  message?: string;
}

export interface FixDependencies {
  project: string;
  package_manager: string;
  status: string; // "plan" | "applied" | "failed"
  // plan (npm dry-run)
  would_change?: { added: number; removed: number; changed: number; updated: number };
  remaining_vulnerabilities?: Record<string, number>;
  remaining_total?: number;
  // plan (pnpm audit)
  vulnerabilities?: Record<string, number>;
  vulnerability_total?: number;
  next?: string;
  note?: string;
  // apply
  command?: string;
  exit_code?: number | null;
  output?: string;
  undo_hint?: string;
  error?: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = b.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const WORKFLOWS: { id: string; label: string; needs?: "issue" | "target" }[] = [
  { id: "dev_setup", label: "Dev setup" },
  { id: "code_review", label: "Code review" },
  { id: "architecture_analysis", label: "Architecture" },
  { id: "performance_audit", label: "Performance" },
  { id: "debug_investigation", label: "Debug", needs: "issue" },
  { id: "refactor_planning", label: "Refactor", needs: "target" },
];

export const smartdev = {
  base: BASE,
  health: () => fetch(`${BASE}/api/health`).then((r) => r.json()),
  analyze: (path: string, opts?: { diff_base?: string }) =>
    post<Analysis>("/api/analyze", { path, ...opts }),
  lint: (path: string, opts?: { typecheck?: boolean; diff_base?: string }) =>
    post<LintResult>("/api/lint", { path, ...opts }),
  fixDependencies: (path: string, opts?: { confirm?: boolean; force?: boolean }) =>
    post<FixDependencies>("/api/dependencies/fix", { path, ...opts }),
  workflow: (name: string, body: { project_path?: string; issue?: string; target?: string }) =>
    post<WorkflowResult>(`/api/workflow/${name}`, body),
  // ChatClient surface
  agentStatus: () => fetch(`${BASE}/api/agent`).then((r) => r.json() as Promise<AgentStatus>),
  resetSession: (id: string) =>
    fetch(`${BASE}/api/chat/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => r.json()),
  chatStream: (message: string, sessionId: string | null) => streamChat(BASE, message, sessionId),
} satisfies ChatClient & Record<string, unknown>;
