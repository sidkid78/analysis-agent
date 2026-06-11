"""Transport-neutral agent interface, events, and result types.

Any concrete agent (Gemini today, antigravity-sdk later) implements
:class:`AnalysisAgent`. The agent owns conversation state keyed by ``session_id``
so multi-turn chats keep their full tool-call context, and streams
:class:`AgentEvent` objects so the HTTP layer can forward them over SSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol


@dataclass
class AgentToolCall:
    """One function call the agent made, for a visible trace."""

    name: str
    args: dict[str, Any]
    ok: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": self.args, "ok": self.ok, "summary": self.summary}


@dataclass
class AgentEvent:
    """A single streamed event.

    ``type`` is one of: ``session`` (payload: session_id), ``text`` (delta),
    ``tool`` (name/args/ok/summary), ``chart`` (spec), ``done`` (model),
    ``error`` (message).
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.payload}


@dataclass
class AgentResult:
    """Aggregated result of consuming a stream (used by ``run`` / tests)."""

    reply: str
    model: str
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "model": self.model,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "charts": self.charts,
        }


class AgentError(Exception):
    """Agent-level failure surfaced to the caller (e.g. missing API key)."""


class AnalysisAgent(Protocol):
    name: str

    def stream(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        """Stream the agent's work for ``message`` within ``session_id``."""
        ...

    def reset(self, session_id: str) -> None:
        """Forget a session's conversation history."""
        ...
