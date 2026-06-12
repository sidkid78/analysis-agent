"""Workflow prompts — guided, multi-step development workflows.

Each returns a Markdown string that primes the agent with findings and/or a
methodology, then points at the concrete tool calls to run next.
"""

from .dev_setup import dev_setup
from .code_review import code_review
from .architecture_analysis import architecture_analysis
from .debug_investigation import debug_investigation
from .refactor_planning import refactor_planning
from .performance_audit import performance_audit

__all__ = [
    "dev_setup",
    "code_review",
    "architecture_analysis",
    "debug_investigation",
    "refactor_planning",
    "performance_audit",
]
