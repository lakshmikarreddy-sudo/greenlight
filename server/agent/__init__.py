"""Agent orchestration package for Greenlight."""

from server.agent.events import (
    AgentEvent,
    EventType,
    adapt_adk_event,
    create_event,
)
from server.agent.greenlight_agent import (
    GreenlightOrchestrator,
    create_greenlight_agent,
)
from server.agent.prompts import (
    AGENT_SYSTEM_INSTRUCTION,
    RESEARCH_TRIAGE_PROMPT,
    RISK_SYNTHESIS_PROMPT,
    SCREENPLAY_EXTRACTION_PROMPT,
)

__all__ = [
    "create_greenlight_agent",
    "GreenlightOrchestrator",
    "AgentEvent",
    "EventType",
    "create_event",
    "adapt_adk_event",
    "AGENT_SYSTEM_INSTRUCTION",
    "SCREENPLAY_EXTRACTION_PROMPT",
    "RESEARCH_TRIAGE_PROMPT",
    "RISK_SYNTHESIS_PROMPT",
]
