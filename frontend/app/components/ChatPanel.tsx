"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ChartSpec, type ChatToolCall } from "../lib/api";
import { Chart } from "./Chart";
import { Markdown } from "./Markdown";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls: ChatToolCall[];
  charts: ChartSpec[];
  streaming?: boolean;
}

const SUGGESTIONS = [
  "Load the employee survey and tell me what drives satisfaction",
  "What's in the ecommerce orders data? Chart sales by region.",
  "Find the strongest correlations in product performance",
];

export function ChatPanel({ onActivity }: { onActivity?: () => void }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [model, setModel] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attached, setAttached] = useState<{ name: string; rows: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .agentStatus()
      .then((s) => {
        setEnabled(s.enabled);
        setModel(s.model);
      })
      .catch(() => setEnabled(false));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  // Mutate the last (assistant) message in place as events stream in.
  function patchLast(fn: (m: ChatMessage) => ChatMessage) {
    setMessages((cur) => {
      if (cur.length === 0) return cur;
      const copy = cur.slice();
      copy[copy.length - 1] = fn(copy[copy.length - 1]);
      return copy;
    });
  }

  async function uploadFile(file: File) {
    if (!enabled || uploading || busy) return;
    setError(null);
    setUploading(true);
    try {
      const info = await api.upload(file);
      setAttached({ name: info.name, rows: info.rows });
      onActivity?.(); // surface the new dataset in the sidebar
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if ((!trimmed && !attached) || busy || uploading || !enabled) return;
    setError(null);
    setInput("");
    // Let the agent know about a just-uploaded dataset, but keep the bubble clean.
    const display = trimmed || `Give me a first look at "${attached?.name}".`;
    const sent = attached
      ? `(I just uploaded the dataset "${attached.name}" with ${attached.rows} rows — ` +
        `it is loaded and ready to analyze.) ${display}`
      : display;
    setAttached(null);
    setMessages((cur) => [
      ...cur,
      { role: "user", content: display, toolCalls: [], charts: [] },
      { role: "assistant", content: "", toolCalls: [], charts: [], streaming: true },
    ]);
    setBusy(true);
    let activity = false;
    try {
      for await (const ev of api.chatStream(sent, sessionId)) {
        switch (ev.type) {
          case "session":
            setSessionId(ev.session_id);
            break;
          case "text":
            patchLast((m) => ({ ...m, content: m.content + ev.delta }));
            break;
          case "tool":
            activity = true;
            patchLast((m) => ({
              ...m,
              toolCalls: [
                ...m.toolCalls,
                { name: ev.name, args: ev.args, ok: ev.ok, summary: ev.summary },
              ],
            }));
            break;
          case "chart":
            patchLast((m) => ({ ...m, charts: [...m.charts, ev.spec] }));
            break;
          case "error":
            setError(ev.message);
            break;
          case "done":
            break;
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      patchLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
      if (activity) onActivity?.();
    }
  }

  async function newChat() {
    if (sessionId) api.resetSession(sessionId).catch(() => {});
    setSessionId(null);
    setMessages([]);
    setError(null);
  }

  return (
    <section
      onDragOver={(e) => {
        if (!enabled) return;
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        // ignore drag-leave bubbling from children
        if (e.currentTarget.contains(e.relatedTarget as Node)) return;
        setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) uploadFile(file);
      }}
      className="relative flex h-full flex-col rounded-2xl border border-black/10 bg-white/50 dark:border-white/10 dark:bg-white/[.02]"
    >
      {dragOver && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl border-2 border-dashed border-indigo-400 bg-indigo-50/80 text-sm font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
          Drop a .json / .csv / .tsv file to analyze
        </div>
      )}
      <div className="flex items-center justify-between border-b border-black/10 px-4 py-3 dark:border-white/10">
        <h2 className="text-sm font-semibold">Ask the data</h2>
        <div className="flex items-center gap-2">
          {enabled !== null && (
            <span className="text-xs text-zinc-500">{enabled ? model : "agent disabled"}</span>
          )}
          {messages.length > 0 && (
            <button
              onClick={newChat}
              disabled={busy}
              className="rounded-md border border-black/15 px-2 py-1 text-xs hover:bg-black/[.03] disabled:opacity-50 dark:border-white/15 dark:hover:bg-white/5"
            >
              New chat
            </button>
          )}
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {enabled === false && (
          <div className="rounded-lg border border-amber-300/50 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
            Chat agent is off. Set <code>GEMINI_API_KEY</code> in the backend
            environment and restart it.
          </div>
        )}

        {messages.length === 0 && enabled && (
          <div className="space-y-2">
            <p className="text-xs text-zinc-500">Try:</p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="block w-full rounded-lg border border-black/10 px-3 py-2 text-left text-xs transition hover:border-indigo-400 hover:bg-indigo-50 dark:border-white/10 dark:hover:bg-indigo-500/10"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {error && (
          <div className="rounded-lg border border-red-300/50 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            {error}
          </div>
        )}
      </div>

      <div className="border-t border-black/10 p-3 dark:border-white/10">
        {(attached || uploading) && (
          <div className="mb-2 flex items-center gap-2 text-xs">
            {uploading ? (
              <span className="flex items-center gap-2 text-zinc-500">
                <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                uploading…
              </span>
            ) : (
              attached && (
                <span className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-2.5 py-1 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
                  📎 {attached.name} · {attached.rows} rows
                  <button
                    onClick={() => setAttached(null)}
                    className="text-indigo-400 hover:text-indigo-600"
                    aria-label="Remove attachment"
                  >
                    ✕
                  </button>
                </span>
              )
            )}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex gap-2"
        >
          <input
            ref={fileRef}
            type="file"
            accept=".json,.csv,.tsv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) uploadFile(file);
              if (fileRef.current) fileRef.current.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={!enabled || busy || uploading}
            title="Attach a .json / .csv / .tsv file"
            aria-label="Attach a file"
            className="rounded-lg border border-black/15 px-3 py-2 text-sm hover:bg-black/[.03] disabled:opacity-50 dark:border-white/15 dark:hover:bg-white/5"
          >
            📎
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              !enabled
                ? "Agent disabled"
                : attached
                  ? "Ask about the uploaded file…"
                  : "Ask about your data…"
            }
            disabled={!enabled || busy}
            className="flex-1 rounded-lg border border-black/15 px-3 py-2 text-sm outline-none focus:border-indigo-400 disabled:opacity-50 dark:border-white/15 dark:bg-transparent"
          />
          <button
            type="submit"
            disabled={!enabled || busy || uploading || (!input.trim() && !attached)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </section>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const empty = !message.content && message.toolCalls.length === 0;
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[92%] ${isUser ? "" : "w-full"}`}>
        {message.toolCalls.length > 0 && (
          <details className="mb-2 text-xs text-zinc-500" open={message.streaming}>
            <summary className="cursor-pointer select-none">
              {message.toolCalls.length} tool call{message.toolCalls.length > 1 ? "s" : ""}
            </summary>
            <ul className="mt-1 space-y-1">
              {message.toolCalls.map((t, i) => (
                <li key={i} className="font-mono">
                  <span className={t.ok ? "text-emerald-600" : "text-red-600"}>
                    {t.ok ? "✓" : "✗"}
                  </span>{" "}
                  {t.name}(
                  {Object.entries(t.args)
                    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                    .join(", ")}
                  )<span className="text-zinc-400"> → {t.summary}</span>
                </li>
              ))}
            </ul>
          </details>
        )}

        {message.content && (
          <div
            className={`rounded-2xl px-3 py-2 text-sm ${
              isUser
                ? "whitespace-pre-wrap bg-indigo-600 text-white"
                : "bg-black/[.04] text-zinc-800 dark:bg-white/[.06] dark:text-zinc-100"
            }`}
          >
            {isUser ? message.content : <Markdown text={message.content} />}
            {message.streaming && message.content && (
              <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-indigo-400 align-middle" />
            )}
          </div>
        )}

        {empty && message.streaming && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
            analyzing…
          </div>
        )}

        {message.charts.map((spec, i) => (
          <div key={i} className="mt-3">
            <Chart spec={spec} />
          </div>
        ))}
      </div>
    </div>
  );
}
