// Client for the Infrastructure Automation FastAPI backend (the "Infra" tab).

import { streamChat, type AgentStatus, type ChatClient } from "./chat";

const BASE = process.env.NEXT_PUBLIC_INFRA_API_BASE ?? "http://127.0.0.1:8040";

export type ServiceStatus = "healthy" | "degraded" | "down";

export interface Service {
  name: string;
  environment: string;
  version: string;
  replicas: number;
  status: ServiceStatus;
  cpu_percent: number;
  memory_percent: number;
  error_rate: number;
  latency_ms: number;
  tags: string[];
}

export interface ResourceInfo {
  kind: string;
  capacity: number;
  utilization: number;
  unit: string;
  auto_scaling: boolean;
}

export interface Secret {
  name: string;
  kind: string;
  environment: string;
  age_days: number;
  rotation_interval_days: number;
  due: boolean;
}

export interface BackupRecord {
  backup_id: string;
  data_source: string;
  backup_type: string;
  size_gb: number;
  retention_days: number;
  verified: boolean;
  created_at: string;
}

export interface Deployment {
  deployment_id: string;
  app_name: string;
  environment: string;
  strategy: string;
  from_version: string;
  to_version: string;
  status: string;
  at: string;
}

export interface Snapshot {
  clock: number;
  services: Service[];
  resources: ResourceInfo[];
  secrets: Secret[];
  backups: BackupRecord[];
  deployments: Deployment[];
}

export interface MonitorAlert {
  service: string;
  severity: "warning" | "critical";
  reasons: string[];
}

export interface MonitorResult {
  summary: {
    total: number;
    healthy: number;
    degraded: number;
    down: number;
    alerting: number;
    overall: ServiceStatus;
  };
  services: Service[];
  alerts: MonitorAlert[];
}

export interface LogSample {
  level: string;
  service: string;
  message: string;
  count: number;
}

export interface LogsResult {
  total_matched: number;
  by_level: Record<string, number>;
  top_patterns: { level: string; pattern: string; count: number }[];
  anomalies: { service: string; status: string; error_rate: number; projected_errors: number; note: string }[];
  samples: LogSample[];
}

export interface WorkflowResult {
  workflow: string;
  markdown: string;
}

export const WORKFLOWS: { id: string; label: string }[] = [
  { id: "infra-health-check", label: "Health check" },
  { id: "deployment-strategy", label: "Deployment strategy" },
  { id: "scaling-analysis", label: "Scaling analysis" },
  { id: "incident-response", label: "Incident response" },
  { id: "security-audit", label: "Security audit" },
  { id: "disaster-recovery", label: "Disaster recovery" },
];

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
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

export const infra = {
  base: BASE,
  health: () => get<{ status: string }>("/api/health"),
  fleet: () => get<Snapshot>("/api/fleet"),
  reset: () => post<{ reset: boolean }>("/api/fleet/reset", {}),
  monitor: (service_filter = "all", metrics = "detailed", alert_threshold = 80) =>
    get<MonitorResult>(
      `/api/monitor?service_filter=${encodeURIComponent(service_filter)}&metrics=${metrics}&alert_threshold=${alert_threshold}`,
    ),
  logs: (body: { log_source?: string; time_range?: string; log_level?: string; pattern?: string }) =>
    post<LogsResult>("/api/logs", body),
  workflow: (name: string, arg = "", arg2 = "") =>
    get<WorkflowResult>(
      `/api/workflows/${encodeURIComponent(name)}?arg=${encodeURIComponent(arg)}&arg2=${encodeURIComponent(arg2)}`,
    ),
  // ChatClient surface (reuses the shared SSE parser)
  agentStatus: () => get<AgentStatus>("/api/agent"),
  resetSession: (id: string) =>
    fetch(`${BASE}/api/chat/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => r.json()),
  chatStream: (message: string, sessionId: string | null) => streamChat(BASE, message, sessionId),
} satisfies ChatClient & Record<string, unknown>;
