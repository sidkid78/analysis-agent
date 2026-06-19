"""Agentic workflow prompts.

Each returns guided Markdown that composes the fleet tools and tells the agent
what to do next — the high-leverage primitive. Deliberately concise: they run
real tools against the live fleet rather than emitting giant static templates.
"""

from .deployment_strategy import deployment_strategy_prompt
from .disaster_recovery import disaster_recovery_prompt
from .incident_response import incident_response_prompt
from .infra_health_check import infra_health_check_prompt
from .scaling_analysis import scaling_analysis_prompt
from .security_audit import security_audit_prompt

__all__ = [
    "deployment_strategy_prompt",
    "disaster_recovery_prompt",
    "incident_response_prompt",
    "infra_health_check_prompt",
    "scaling_analysis_prompt",
    "security_audit_prompt",
]
