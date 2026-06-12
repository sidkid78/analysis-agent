"""In-app dev agent — a Gemini analyst that drives the smart-dev tools.

Mirrors the Quick Data agent: an :class:`AnalysisAgent` protocol with a
streaming, session-persistent Gemini implementation, decoupled from the FastAPI
transport.
"""

from .base import AgentError, AgentEvent, AgentResult, AgentToolCall, AnalysisAgent

__all__ = [
    "AnalysisAgent",
    "AgentError",
    "AgentEvent",
    "AgentResult",
    "AgentToolCall",
]
