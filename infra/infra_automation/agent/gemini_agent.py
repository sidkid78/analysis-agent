"""Gemini-backed SRE agent (google-genai SDK).

Streaming manual function-calling loop with server-side session persistence.
Gemini 3 requires the function-call part's ``thought_signature`` to round-trip,
so original part objects are re-sent rather than rebuilt.
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterator

from . import tools
from .base import AgentError, AgentEvent, AgentResult, AgentToolCall

DEFAULT_MODEL = "gemini-3.5-flash"
MAX_STEPS = 25
MAX_SESSIONS = 200

SYSTEM_INSTRUCTION = """\
You are an SRE assistant operating a simulated service fleet through the provided
tools. Use real tool results — never invent service names, metrics, or versions.

Workflow:
- Start with monitor_services (or fleet_status) to understand current state.
- Use analyze_logs to investigate degraded services and incidents.
- deploy_application, scale_resources, backup_data, and rotate_secrets are
  MUTATING. They PLAN by default. Only pass confirm=True AFTER the user explicitly
  approves the specific plan — never apply a change unprompted.
- Prefer the smallest safe action. Before risky changes, suggest a backup.

Be concrete: cite service names, real numbers, and version strings from tool
results. End with a clear, actionable next step. Keep it tight."""


@dataclass
class _Session:
    contents: list[Any] = field(default_factory=list)


class _SessionStore:
    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._d: "OrderedDict[str, _Session]" = OrderedDict()
        self._max = max_sessions

    def touch(self, session_id: str) -> _Session:
        s = self._d.get(session_id)
        if s is None:
            s = _Session()
            self._d[session_id] = s
            while len(self._d) > self._max:
                self._d.popitem(last=False)
        self._d.move_to_end(session_id)
        return s

    def drop(self, session_id: str) -> None:
        self._d.pop(session_id, None)


def _summarize(name: str, result: dict[str, Any]) -> tuple[bool, str]:
    if isinstance(result, dict) and "error" in result:
        return False, str(result["error"])
    if name == "monitor_services":
        s = result.get("summary", {})
        return True, f"{s.get('overall')}: {s.get('healthy')} healthy / {s.get('degraded')} degraded, {s.get('alerting')} alert(s)"
    if name == "analyze_logs":
        return True, f"{result.get('total_matched')} entries, {len(result.get('anomalies', []))} anomaly(ies)"
    if name == "fleet_status":
        return True, f"{len(result.get('services', []))} services"
    if name in ("deploy_application", "scale_resources", "backup_data", "rotate_secrets"):
        return True, "planned" if result.get("planned") else "applied"
    return True, "ok"


class GeminiAgent:
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("INFRA_MODEL") or os.getenv("QUICKDATA_MODEL", DEFAULT_MODEL)
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None
        self._sessions = _SessionStore()

    def _client_or_raise(self):
        if not self._api_key:
            raise AgentError(
                "No Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) to enable the agent."
            )
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def reset(self, session_id: str) -> None:
        self._sessions.drop(session_id)

    def stream(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        from google.genai import types

        client = self._client_or_raise()
        session = self._sessions.touch(session_id)
        session.contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tools.TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )

        for _ in range(MAX_STEPS):
            text_accum = ""
            calls: list[Any] = []
            fc_parts: list[Any] = []

            for chunk in client.models.generate_content_stream(
                model=self.model, contents=session.contents, config=config
            ):
                cands = chunk.candidates or []
                content = cands[0].content if cands else None
                for part in (content.parts if content and content.parts else []):
                    fc = getattr(part, "function_call", None)
                    if fc:
                        calls.append(fc)
                        fc_parts.append(part)  # keep thought_signature
                        continue
                    text = getattr(part, "text", None)
                    if text:
                        text_accum += text
                        yield AgentEvent("text", {"delta": text})

            model_parts: list[Any] = []
            if text_accum:
                model_parts.append(types.Part.from_text(text=text_accum))
            model_parts.extend(fc_parts)
            if model_parts:
                session.contents.append(types.Content(role="model", parts=model_parts))

            if not calls:
                yield AgentEvent("done", {"model": self.model})
                return

            tool_parts: list[Any] = []
            for fc in calls:
                args = dict(fc.args or {})
                fn = tools.TOOLS_BY_NAME.get(fc.name)
                if fn is None:
                    result: dict[str, Any] = {"error": f"Unknown tool '{fc.name}'"}
                else:
                    try:
                        result = fn(**args)
                    except Exception as exc:
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                ok, summary = _summarize(fc.name, result)
                yield AgentEvent("tool", {"name": fc.name, "args": args, "ok": ok, "summary": summary})
                tool_parts.append(types.Part.from_function_response(name=fc.name, response=_wrap(result)))
            session.contents.append(types.Content(role="tool", parts=tool_parts))

        yield AgentEvent("text", {"delta": "\n\n(Stopped after the maximum number of steps.)"})
        yield AgentEvent("done", {"model": self.model})

    def run(self, session_id: str, message: str) -> AgentResult:
        reply = ""
        calls: list[AgentToolCall] = []
        for ev in self.stream(session_id, message):
            if ev.type == "text":
                reply += ev.payload["delta"]
            elif ev.type == "tool":
                calls.append(AgentToolCall(**ev.payload))
        return AgentResult(reply=reply.strip() or "(no response)", model=self.model, tool_calls=calls)


def _wrap(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"result": result}
    return json.loads(json.dumps(result, default=str))
