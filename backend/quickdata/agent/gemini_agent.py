"""Gemini-backed analysis agent (google-genai SDK).

Streams a manual function-calling loop so the UI sees text deltas, tool calls,
and charts as they happen. Conversation state — including the model's
function-call turns and the tool responses — is persisted per session, so a
follow-up question retains the full context of earlier analysis.
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
MAX_STEPS = 8
MAX_SESSIONS = 200

SYSTEM_INSTRUCTION = """\
You are Quick Data, a concise data analyst working over JSON/CSV datasets held \
in memory. Use the provided tools to do real analysis — never invent numbers.

Workflow:
- Call list_datasets to see what is loaded. If nothing relevant is loaded, call \
list_samples and load_sample to load a bundled dataset.
- Use dataset_breakdown to understand columns before analyzing.
- Use segment_by_column, find_correlations, and create_chart for focused answers.
- Use run_query for arbitrary questions (filter / group-by / aggregate / top-N) —
  e.g. filters=["region==East Coast"], group_by=["category"], metrics=["sales:sum"].
- Use profile_dataset to assess data quality, and clean_dataset to fix issues
  (it writes a new "<name>_clean" dataset; analyze that afterward).
- For broad requests ("analyze this", "give me a report"), prefer run_playbook
  (first_look / data_quality_audit / correlation_deep_dive) or generate_report.
- When a chart helps, call create_chart — it renders in the UI, so don't describe \
it pixel by pixel.

Reply in plain language: state the finding, cite the concrete numbers from tool \
results, and suggest a sensible next step. Keep it tight. Across a conversation, \
build on datasets and findings already established rather than reloading."""


@dataclass
class _Session:
    contents: list[Any] = field(default_factory=list)


class _SessionStore:
    """In-memory, bounded (LRU) store of per-session SDK conversation history."""

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
    """Short human-readable summary of a tool result for the trace."""
    if isinstance(result, dict) and "error" in result:
        return False, str(result["error"])
    if name == "list_datasets":
        ds = result.get("datasets", [])
        return True, (f"{len(ds)} dataset(s): " + ", ".join(d["name"] for d in ds)) if ds else "no datasets loaded"
    if name == "list_samples":
        return True, ", ".join(result.get("samples", [])) or "no samples"
    if name == "load_sample":
        info = result.get("loaded", {})
        return True, f"loaded {info.get('name')} ({info.get('rows')} rows)"
    if name == "dataset_breakdown":
        return True, f"{result.get('rows')} rows, {len(result.get('columns', []))} columns"
    if name == "find_correlations":
        return True, f"{len(result.get('correlations', []))} correlation(s) >= threshold"
    if name == "segment_by_column":
        return True, f"{len(result.get('segments', []))} segments of '{result.get('column')}'"
    if name == "create_chart":
        return True, f"{result.get('type')} chart: {result.get('title')}"
    if name == "suggest_analysis":
        return True, f"{len(result.get('suggestions', []))} suggestion(s)"
    if name == "run_query":
        return True, f"{result.get('result_rows')} result row(s) from {result.get('matched_rows')} matched"
    if name == "profile_dataset":
        return True, f"quality {result.get('quality_score')}/100, {len(result.get('issues', []))} issue(s)"
    if name == "clean_dataset":
        return True, f"-> '{result.get('cleaned_dataset')}' ({result.get('rows_after')} rows)"
    if name == "run_playbook":
        return True, result.get("summary", "playbook done")
    if name == "generate_report":
        return True, f"report ready ({len(result.get('charts', []))} chart(s))"
    return True, "ok"


class GeminiAgent:
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("QUICKDATA_MODEL", DEFAULT_MODEL)
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None  # lazy: don't fail import when no key is set
        self._sessions = _SessionStore()

    def _client_or_raise(self):
        if not self._api_key:
            raise AgentError(
                "No Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in the "
                "backend environment to enable the chat agent."
            )
        if self._client is None:
            from google import genai  # imported lazily

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
            fc_parts: list[Any] = []  # original part objects (keep thought_signature)

            for chunk in client.models.generate_content_stream(
                model=self.model, contents=session.contents, config=config
            ):
                cands = chunk.candidates or []
                content = cands[0].content if cands else None
                for part in (content.parts if content and content.parts else []):
                    fc = getattr(part, "function_call", None)
                    if fc:
                        calls.append(fc)
                        # Re-send the original part as-is: Gemini 3 requires the
                        # thought_signature on function-call parts to round-trip.
                        fc_parts.append(part)
                        continue
                    text = getattr(part, "text", None)
                    if text:
                        text_accum += text
                        yield AgentEvent("text", {"delta": text})

            # Persist the model's turn (text + any function calls) to history.
            model_parts: list[Any] = []
            if text_accum:
                model_parts.append(types.Part.from_text(text=text_accum))
            model_parts.extend(fc_parts)
            if model_parts:
                session.contents.append(types.Content(role="model", parts=model_parts))

            if not calls:
                yield AgentEvent("done", {"model": self.model})
                return

            # Execute the calls, stream results, persist tool responses.
            tool_parts: list[Any] = []
            for fc in calls:
                args = dict(fc.args or {})
                fn = tools.TOOLS_BY_NAME.get(fc.name)
                if fn is None:
                    result: dict[str, Any] = {"error": f"Unknown tool '{fc.name}'"}
                else:
                    try:
                        result = fn(**args)
                    except Exception as exc:  # surface to model rather than crash
                        result = {"error": f"{type(exc).__name__}: {exc}"}

                ok, summary = _summarize(fc.name, result)
                yield AgentEvent("tool", {"name": fc.name, "args": args, "ok": ok, "summary": summary})
                # Surface charts whether returned directly or nested (playbooks/report).
                if tools.is_chart_spec(result):
                    yield AgentEvent("chart", {"spec": result})
                elif isinstance(result, dict) and isinstance(result.get("charts"), list):
                    for spec in result["charts"]:
                        if tools.is_chart_spec(spec):
                            yield AgentEvent("chart", {"spec": spec})

                tool_parts.append(
                    types.Part.from_function_response(name=fc.name, response=_wrap(result))
                )
            session.contents.append(types.Content(role="tool", parts=tool_parts))

        yield AgentEvent("text", {"delta": "\n\n(Stopped after the maximum number of analysis steps.)"})
        yield AgentEvent("done", {"model": self.model})

    def run(self, session_id: str, message: str) -> AgentResult:
        """Consume the stream into an aggregated result (convenience / tests)."""
        reply = ""
        tool_calls: list[AgentToolCall] = []
        charts: list[dict[str, Any]] = []
        for ev in self.stream(session_id, message):
            if ev.type == "text":
                reply += ev.payload["delta"]
            elif ev.type == "tool":
                tool_calls.append(AgentToolCall(**ev.payload))
            elif ev.type == "chart":
                charts.append(ev.payload["spec"])
        return AgentResult(
            reply=reply.strip() or "(no response)",
            model=self.model,
            tool_calls=tool_calls,
            charts=charts,
        )


def _wrap(result: dict[str, Any]) -> dict[str, Any]:
    """Function responses must be JSON objects; ensure dict + JSON-safe."""
    if not isinstance(result, dict):
        return {"result": result}
    return json.loads(json.dumps(result, default=str))
