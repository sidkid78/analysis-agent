"use client";

import { useEffect, useRef, useState } from "react";

import type { ChartSpec } from "../lib/api";
import type { ChatClient, ChatToolCall } from "../lib/chat";
import { Markdown } from "./Markdown";

interface Msg {
  role: "user" | "agent";
  text: string;
  tools: ChatToolCall[];
  charts: ChartSpec[];
}

export interface AgentChatProps {
  client: ChatClient;
  title: string;
  placeholder: string;
  footer?: string;
  suggestions?: string[];
  showCharts?: boolean;
  /** Static chip shown above the composer (e.g. project path / context). */
  contextChip?: string | null;
  /** Prefix prepended to the *sent* message (not shown in the bubble). */
  contextPrefix?: () => string | null;
  /** Called after each completed turn (e.g. to refresh a shared store). */
  onActivity?: () => void;
  /** Programmatic send: bump `nonce` to send `text`. */
  inject?: { text: string; nonce: number };
}

export function AgentChat({
  client,
  title,
  placeholder,
  footer,
  suggestions = [],
  showCharts = false,
  contextChip = null,
  contextPrefix,
  onActivity,
  inject,
}: AgentChatProps) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const lastNonce = useRef<number>(-1);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function patchAgent(update: (m: Msg) => Msg) {
    setMessages((prev) => {
      const copy = [...prev];
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === "agent") {
          copy[i] = update(copy[i]);
          break;
        }
      }
      return copy;
    });
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", text: trimmed, tools: [], charts: [] },
      { role: "agent", text: "", tools: [], charts: [] },
    ]);
    setStreaming(true);
    const prefix = contextPrefix?.() ?? null;
    const sent = prefix ? `${prefix}\n\n${trimmed}` : trimmed;
    try {
      for await (const ev of client.chatStream(sent, sessionRef.current)) {
        if (ev.type === "session") sessionRef.current = ev.session_id;
        else if (ev.type === "text") patchAgent((a) => ({ ...a, text: a.text + ev.delta }));
        else if (ev.type === "tool") patchAgent((a) => ({ ...a, tools: [...a.tools, ev] }));
        else if (ev.type === "chart" && showCharts) patchAgent((a) => ({ ...a, charts: [...a.charts, ev.spec] }));
        else if (ev.type === "error") patchAgent((a) => ({ ...a, text: `${a.text}\n\n⚠️ ${ev.message}` }));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      patchAgent((a) => ({ ...a, text: `${a.text}\n\n⚠️ ${msg}` }));
    } finally {
      setStreaming(false);
      onActivity?.();
    }
  }

  // Programmatic send from the parent (suggestion clicks in the main canvas).
  useEffect(() => {
    if (inject && inject.nonce !== lastNonce.current) {
      lastNonce.current = inject.nonce;
      void send(inject.text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inject?.nonce]);

  async function newChat() {
    if (sessionRef.current) client.resetSession(sessionRef.current).catch(() => {});
    sessionRef.current = null;
    setMessages([]);
  }

  return (
    <div style={{ width: 384, flex: "none", borderLeft: "1px solid var(--line)", background: "var(--panel)", display: "flex", flexDirection: "column" }}>
      <div style={{ height: 54, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 18px", borderBottom: "1px solid var(--line)" }}>
        <div style={{ width: 24, height: 24, borderRadius: 7, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 8, height: 8, background: "var(--accent-ink)", transform: "rotate(45deg)", borderRadius: 1.5 }} />
        </div>
        <span style={{ fontSize: 14, fontWeight: 600 }}>{title}</span>
        <button onClick={newChat} style={{ marginLeft: "auto", fontSize: 12, color: "var(--ink-3)", border: "1px solid var(--line)", background: "transparent", borderRadius: 8, padding: "4px 10px" }}>
          New chat
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
        {messages.length === 0 && suggestions.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Try:</div>
            {suggestions.map((q) => (
              <button key={q} onClick={() => send(q)} style={{ textAlign: "left", border: "1px solid var(--line)", background: "var(--panel-2)", borderRadius: 10, padding: "9px 11px", fontSize: 12, color: "var(--ink-2)" }}>
                {q}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} style={{ alignSelf: "flex-end", maxWidth: "84%", background: "var(--accent)", color: "var(--accent-ink)", padding: "10px 13px", borderRadius: "14px 14px 4px 14px", fontSize: 13 }}>
              {m.text}
            </div>
          ) : (
            <div key={i} style={{ display: "flex", gap: 10 }}>
              <div style={{ width: 24, height: 24, flex: "none", borderRadius: 7, background: "var(--accent-tint)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ width: 7, height: 7, background: "var(--accent)", transform: "rotate(45deg)", borderRadius: 1.5 }} />
              </div>
              <div style={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
                {m.tools.length > 0 && (
                  <div style={{ border: "1px solid var(--line)", borderRadius: 11, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 11px", background: "var(--panel-2)", fontSize: 12, color: "var(--ink-2)" }}>
                      {m.tools.length} tool call{m.tools.length > 1 ? "s" : ""}
                      <span className="mono" style={{ marginLeft: "auto", fontSize: 10, color: m.tools.every((t) => t.ok) ? "var(--ok)" : "var(--crit)" }}>
                        {m.tools.every((t) => t.ok) ? "done" : "error"}
                      </span>
                    </div>
                    <div className="mono" style={{ padding: "9px 11px", fontSize: 11, lineHeight: 1.9, color: "var(--ink-2)" }}>
                      {m.tools.map((t, ti) => (
                        <div key={ti}>
                          <span style={{ color: t.ok ? "var(--ok)" : "var(--crit)" }}>{t.ok ? "✓" : "✕"}</span> {t.name}{" "}
                          <span style={{ color: "var(--ink-3)" }}>→ {t.summary}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {(m.text || streaming) && (
                  <div style={{ background: "var(--panel-2)", border: "1px solid var(--line)", padding: "11px 13px", borderRadius: "4px 14px 14px 14px", fontSize: 13, lineHeight: 1.55 }}>
                    {m.text ? <Markdown text={m.text} /> : <span style={{ color: "var(--ink-3)" }}>thinking…</span>}
                  </div>
                )}
                {m.charts.map((spec, ci) => (
                  <ChartMini key={ci} spec={spec} />
                ))}
              </div>
            </div>
          ),
        )}
        <div ref={endRef} />
      </div>

      <div style={{ flex: "none", padding: 14, borderTop: "1px solid var(--line)" }}>
        {contextChip && (
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 9, fontSize: 11, color: "var(--ink-3)" }}>
            <span className="mono" style={{ background: "var(--chip)", border: "1px solid var(--line)", borderRadius: 6, padding: "2px 7px" }}>{contextChip}</span>
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          style={{ display: "flex", alignItems: "center", gap: 8, border: "1px solid var(--line)", background: "var(--panel-2)", borderRadius: 13, padding: "7px 7px 7px 12px" }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder}
            style={{ flex: 1, fontSize: 13, color: "var(--ink)", background: "transparent", border: "none", outline: "none" }}
          />
          <button type="submit" disabled={streaming || !input.trim()} style={{ width: 32, height: 32, borderRadius: 9, background: "var(--accent)", color: "var(--accent-ink)", border: "none", display: "flex", alignItems: "center", justifyContent: "center" }}>
            ↑
          </button>
        </form>
        {footer && <div style={{ textAlign: "center", fontSize: 10, color: "var(--ink-3)", marginTop: 8 }}>{footer}</div>}
      </div>
    </div>
  );
}

function ChartMini({ spec }: { spec: ChartSpec }) {
  const isXY = spec.data.length > 0 && "x" in spec.data[0];
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 13, padding: 14, background: "var(--panel)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{spec.title}</span>
        <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>{spec.type}</span>
      </div>
      {isXY ? (
        <div style={{ position: "relative", height: 104, borderLeft: "1px solid var(--line)", borderBottom: "1px solid var(--line)" }}>
          {(() => {
            const pts = spec.data as { x: number; y: number }[];
            const xs = pts.map((p) => p.x);
            const ys = pts.map((p) => p.y);
            const xmin = Math.min(...xs), xmax = Math.max(...xs);
            const ymin = Math.min(...ys), ymax = Math.max(...ys);
            const nx = (v: number) => (xmax === xmin ? 50 : ((v - xmin) / (xmax - xmin)) * 92 + 4);
            const ny = (v: number) => (ymax === ymin ? 50 : ((v - ymin) / (ymax - ymin)) * 88 + 6);
            return pts.slice(0, 80).map((p, i) => (
              <span key={i} style={{ position: "absolute", left: `${nx(p.x)}%`, bottom: `${ny(p.y)}%`, width: 6, height: 6, borderRadius: "50%", background: "var(--accent)" }} />
            ));
          })()}
        </div>
      ) : (
        (() => {
          const bars = spec.data as { label: string; value: number }[];
          const max = Math.max(1, ...bars.map((b) => b.value));
          return (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 104 }}>
              {bars.slice(0, 8).map((b, i) => (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%", gap: 5 }}>
                  <span className="mono" style={{ fontSize: 9, color: "var(--ink-3)" }}>{fmtNum(b.value)}</span>
                  <div style={{ width: "100%", height: `${(b.value / max) * 88 + 6}%`, background: i === bars.length - 1 ? "var(--accent)" : "var(--accent-soft)", borderRadius: "4px 4px 0 0" }} />
                  <span className="mono" style={{ fontSize: 9, color: "var(--ink-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "100%" }}>{b.label}</span>
                </div>
              ))}
            </div>
          );
        })()
      )}
    </div>
  );
}

function fmtNum(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return `${Math.round(v * 100) / 100}`;
}
