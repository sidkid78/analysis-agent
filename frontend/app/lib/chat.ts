// Shared chat primitives used by both the Quick Data and Smart Dev agents.

import type { ChartSpec } from "./api";

export interface ChatToolCall {
  name: string;
  args: Record<string, unknown>;
  ok: boolean;
  summary: string;
}

export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "text"; delta: string }
  | ({ type: "tool" } & ChatToolCall)
  | { type: "chart"; spec: ChartSpec }
  | { type: "done"; model: string }
  | { type: "error"; message: string };

export interface AgentStatus {
  enabled: boolean;
  model: string;
  backend?: string;
}

// Minimal interface a ChatPanel needs from an API client.
export interface ChatClient {
  agentStatus(): Promise<AgentStatus>;
  resetSession(sessionId: string): Promise<unknown>;
  chatStream(message: string, sessionId: string | null): AsyncGenerator<ChatEvent>;
}

// Optional attach/drag-drop upload behavior for a ChatPanel.
export interface Attached {
  name: string;
  detail: string;
}

export interface UploadConfig {
  accept: string;
  hint: string; // drag-overlay text
  upload(file: File): Promise<Attached>;
  contextNote(a: Attached): string; // prepended to the sent message
}

// Parse an SSE chat stream from `${base}/api/chat`.
export async function* streamChat(
  base: string,
  message: string,
  sessionId: string | null,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${base}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok || !res.body) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (payload) yield JSON.parse(payload) as ChatEvent;
    }
  }
}
