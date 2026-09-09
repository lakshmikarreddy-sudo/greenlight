"""Semantic event adapter for Greenlight ADK workflows.

Converts internal agent events and telemetry into clean, user-facing progress events.
Adheres strictly to security requirements:
- Never exposes API keys, credentials, or auth headers.
- Never exposes internal stack traces or raw python exceptions.
- Never exposes private chain-of-thought or raw unformatted model reasoning.
- Formats visible progress as concise, professional film production telemetry.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Semantic event types for Greenlight production intelligence analysis."""
    ANALYSIS_STARTED = "analysis_started"
    SCREENPLAY_PARSED = "screenplay_parsed"
    DEPENDENCY_DETECTED = "dependency_detected"
    RESEARCH_STARTED = "research_started"
    PARALLEL_SEARCH_INVOKED = "parallel_search_invoked"
    EVIDENCE_RECEIVED = "evidence_received"
    DEPENDENCY_ASSESSED = "dependency_assessed"
    MITIGATION_GENERATED = "mitigation_generated"
    BRIEF_GENERATED = "brief_generated"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_ERROR = "analysis_error"


class AgentEvent(BaseModel):
    """Clean, user-facing workflow event suitable for SSE streaming and UI display."""
    event_type: EventType = Field(..., description="Semantic category of the workflow step")
    stage: str = Field(..., description="Phase identifier: INGESTION, EXTRACTION, RESEARCH, SYNTHESIS, BRIEF")
    message: str = Field(..., description="User-facing status narrative (e.g. 'Researching FAA night drone permits')")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Sanitized, user-facing payload (e.g. scene counts, query names, source titles)"
    )


def create_event(
    event_type: EventType,
    stage: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> AgentEvent:
    """Helper to emit a sanitized AgentEvent.

    Ensures that any accidental credentials or internal keys are stripped from data payloads.
    """
    sanitized_data = None
    if data:
        # Shallow copy and purge sensitive keys
        sanitized_data = {}
        for k, v in data.items():
            if any(secret_term in k.lower() for secret_term in ["key", "secret", "token", "password", "auth"]):
                continue
            sanitized_data[k] = v

    return AgentEvent(
        event_type=event_type,
        stage=stage,
        message=message,
        data=sanitized_data,
    )


def adapt_adk_event(raw_adk_event: Any) -> Optional[AgentEvent]:
    """Inspects a raw Google ADK Event object and converts it into a clean AgentEvent.

    Returns None if the event is low-level framework telemetry that should not be displayed.
    """
    if raw_adk_event is None:
        return None

    # Check if raw_adk_event has content with function calls
    content = getattr(raw_adk_event, "content", None)
    if content:
        parts = getattr(content, "parts", [])
        for part in parts:
            # Check for FunctionCall (tool invocation)
            func_call = getattr(part, "function_call", None)
            if func_call:
                tool_name = getattr(func_call, "name", "tool")
                if tool_name == "parallel_search":
                    args = getattr(func_call, "args", {}) or {}
                    obj = args.get("objective", "Investigating external regulatory dependency")
                    queries = args.get("search_queries", [])
                    return create_event(
                        event_type=EventType.PARALLEL_SEARCH_INVOKED,
                        stage="RESEARCH",
                        message=f"Invoking Parallel Search: {obj}",
                        data={"queries": queries[:3]},
                    )

            # Check for FunctionResponse (tool return)
            func_resp = getattr(part, "function_response", None)
            if func_resp:
                tool_name = getattr(func_resp, "name", "tool")
                if tool_name == "parallel_search":
                    resp_dict = getattr(func_resp, "response", {}) or {}
                    sources = resp_dict.get("sources", [])
                    return create_event(
                        event_type=EventType.EVIDENCE_RECEIVED,
                        stage="RESEARCH",
                        message=f"Received {len(sources)} verified source citations from Parallel Search",
                        data={"source_count": len(sources)},
                    )

    return None
