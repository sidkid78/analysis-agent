"""In-app analysis agent.

The agent turns natural language into analysis by calling the same
``quickdata.engine`` functions the MCP server and HTTP API expose, via LLM
function calling. The :class:`AnalysisAgent` protocol keeps the transport
(FastAPI) decoupled from the backend (currently google-genai / Gemini), so an
antigravity-sdk implementation can be dropped in later without touching callers.
"""

from .base import AgentError, AgentEvent, AgentResult, AgentToolCall, AnalysisAgent

__all__ = [
    "AnalysisAgent",
    "AgentError",
    "AgentEvent",
    "AgentResult",
    "AgentToolCall",
]
