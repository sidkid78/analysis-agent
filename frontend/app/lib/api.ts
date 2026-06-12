// Typed client for the Quick Data FastAPI backend.
// Base URL is overridable via NEXT_PUBLIC_API_BASE (defaults to local dev).

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8020";

export type ColumnKind = "numerical" | "categorical" | "datetime" | "boolean";

export interface ColumnInfo {
  name: string;
  dtype: string;
  kind: ColumnKind;
  null_count: number;
  unique_count: number;
}

export interface DatasetInfo {
  name: string;
  rows: number;
  column_count: number;
  columns: ColumnInfo[];
  source: string | null;
}

export interface Breakdown {
  dataset: string;
  rows: number;
  columns: ColumnInfo[];
  numerical_columns: string[];
  categorical_columns: string[];
  datetime_columns: string[];
  sample: Record<string, unknown>[];
}

export interface Suggestion {
  title: string;
  operation: "segment" | "correlations" | "chart";
  column?: string;
  why: string;
}

export interface Suggestions {
  dataset: string;
  numerical_columns: string[];
  categorical_columns: string[];
  suggestions: Suggestion[];
}

export interface Segment {
  value: string | number | boolean | null;
  count: number;
  [aggregate: string]: string | number | boolean | null;
}

export interface SegmentResult {
  dataset: string;
  column: string;
  distinct_values: number;
  numeric_aggregates: string[];
  segments: Segment[];
}

export interface Correlation {
  x: string;
  y: string;
  r: number;
  strength: string;
  direction: "positive" | "negative";
}

export interface CorrelationResult {
  dataset: string;
  threshold: number;
  numerical_columns: string[];
  correlations: Correlation[];
}

export type ChartType = "bar" | "pie" | "histogram" | "scatter" | "line";

export interface ChartSpec {
  dataset: string;
  type: ChartType;
  subtype: string | null;
  title: string;
  x_label: string;
  y_label: string;
  data: Array<
    | { label: string; value: number }
    | { x: number; y: number }
  >;
}

export interface PlaybookSection {
  title: string;
  body: string;
}

export interface PlaybookResult {
  playbook: string;
  dataset: string;
  summary: string;
  sections: PlaybookSection[];
  charts: ChartSpec[];
}

export interface ReportResult {
  dataset: string;
  markdown: string;
  html: string;
  charts: ChartSpec[];
}

import { streamChat } from "./chat";

export type { ChatEvent, ChatToolCall } from "./chat";

export interface AgentStatus {
  enabled: boolean;
  model: string;
  backend: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  base: API_BASE,
  health: () => request<{ status: string }>("/api/health"),
  listSamples: () => request<{ samples: string[] }>("/api/samples"),
  loadSample: (filename: string, dataset_name?: string) =>
    request<DatasetInfo>("/api/datasets/load-sample", {
      method: "POST",
      body: JSON.stringify({ filename, dataset_name }),
    }),
  listDatasets: () => request<{ datasets: DatasetInfo[] }>("/api/datasets"),
  deleteDataset: (name: string) =>
    request<{ removed: string }>(`/api/datasets/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  breakdown: (name: string) =>
    request<Breakdown>(`/api/datasets/${encodeURIComponent(name)}/breakdown`),
  suggestions: (name: string) =>
    request<Suggestions>(`/api/datasets/${encodeURIComponent(name)}/suggestions`),
  segment: (name: string, column: string) =>
    request<SegmentResult>(
      `/api/datasets/${encodeURIComponent(name)}/segment?column=${encodeURIComponent(column)}`,
    ),
  correlations: (name: string, threshold = 0.5) =>
    request<CorrelationResult>(
      `/api/datasets/${encodeURIComponent(name)}/correlations?threshold=${threshold}`,
    ),
  chart: (name: string, body: { chart_type: ChartType; x?: string; y?: string; bins?: number }) =>
    request<ChartSpec>(`/api/datasets/${encodeURIComponent(name)}/chart`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  playbook: (name: string, playbook: string) =>
    request<PlaybookResult>(
      `/api/datasets/${encodeURIComponent(name)}/playbook/${encodeURIComponent(playbook)}`,
    ),
  report: (name: string) =>
    request<ReportResult>(`/api/datasets/${encodeURIComponent(name)}/report`),
  async reportPdf(name: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/api/datasets/${encodeURIComponent(name)}/report.pdf`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.blob();
  },
  agentStatus: () => request<AgentStatus>("/api/agent"),
  resetSession: (sessionId: string) =>
    request<{ reset: string }>(`/api/chat/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),
  // Stream the agent's work as Server-Sent Events.
  chatStream: (message: string, sessionId: string | null) =>
    streamChat(API_BASE, message, sessionId),
  async upload(file: File, dataset_name?: string): Promise<DatasetInfo> {
    const form = new FormData();
    form.append("file", file);
    const qs = dataset_name ? `?dataset_name=${encodeURIComponent(dataset_name)}` : "";
    const res = await fetch(`${API_BASE}/api/datasets/upload${qs}`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json() as Promise<DatasetInfo>;
  },
};
