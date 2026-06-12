"""Transport-neutral agent interface, events, and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol


@dataclass
class AgentToolCall:
    name: str
    args: dict[str, Any]
    ok: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": self.args, "ok": self.ok, "summary": self.summary}


@dataclass
class AgentEvent:
    """One streamed event: session | text | tool | done | error."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.payload}


@dataclass
class AgentResult:
    reply: str
    model: str
    tool_calls: list[AgentToolCall] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"reply": self.reply, "model": self.model,
                "tool_calls": [t.to_dict() for t in self.tool_calls]}


class AgentError(Exception):
    """Agent-level failure surfaced to the caller (e.g. missing API key)."""


class AnalysisAgent(Protocol):
    name: str

    def stream(self, session_id: str, message: str) -> Iterator[AgentEvent]:
        ...

    def reset(self, session_id: str) -> None:
        ...
