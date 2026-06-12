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

export interface Analysis {
  root: string;
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
  analyze: (path: string) => post<Analysis>("/api/analyze", { path }),
  workflow: (name: string, body: { project_path?: string; issue?: string; target?: string }) =>
    post<WorkflowResult>(`/api/workflow/${name}`, body),
  // ChatClient surface
  agentStatus: () => fetch(`${BASE}/api/agent`).then((r) => r.json() as Promise<AgentStatus>),
  resetSession: (id: string) =>
    fetch(`${BASE}/api/chat/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => r.json()),
  chatStream: (message: string, sessionId: string | null) => streamChat(BASE, message, sessionId),
} satisfies ChatClient & Record<string, unknown>;
