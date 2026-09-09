"""Unit tests for Greenlight ADK Agent orchestration, events, and prompt workflows."""

import asyncio
import json
import pytest

from server.agent import (
    AGENT_SYSTEM_INSTRUCTION,
    AgentEvent,
    EventType,
    GreenlightOrchestrator,
    RESEARCH_TRIAGE_PROMPT,
    RISK_SYNTHESIS_PROMPT,
    SCREENPLAY_EXTRACTION_PROMPT,
    adapt_adk_event,
    create_event,
    create_greenlight_agent,
)
from server.config import settings
from server.services.jurisdiction import resolve_jurisdiction
from server.models import (
    AssessedDependency,
    DependencyCategory,
    EvidenceConfidence,
    ExecutiveScorecard,
    GreenlightBrief,
    ParallelEvidence,
    ProductionDependency,
    ProductionStatus,
    ResearchConfidence,
    ResearchResult,
    RiskLevel,
    Scene,
    ScreenplayBreakdown,
    SearchSource,
    SettingType,
    Slugline,
    TimeOfDay,
)


def test_agent_instantiation_and_tool_registration():
    """Verifies that create_greenlight_agent initializes with the registered Parallel Search tool."""
    agent = create_greenlight_agent()
    assert agent is not None
    assert agent.name == "greenlight_production_agent"
    assert len(agent.tools) == 1
    tool = agent.tools[0]
    assert tool.name == "parallel_search"
    assert "Parallel Search" in tool.description


def test_prompts_load_successfully():
    """Verifies that all prompt templates are defined and contain required guidelines."""
    assert len(AGENT_SYSTEM_INSTRUCTION) > 100
    assert "Parallel Search" in AGENT_SYSTEM_INSTRUCTION
    assert "CRITICAL GROUNDING RULES" in AGENT_SYSTEM_INSTRUCTION

    assert "Line Producer" in SCREENPLAY_EXTRACTION_PROMPT
    assert "PERMITS_AND_LEGAL" in SCREENPLAY_EXTRACTION_PROMPT

    assert "research_objective" in RESEARCH_TRIAGE_PROMPT
    assert "search_queries" in RESEARCH_TRIAGE_PROMPT

    assert "Executive Scorecard" in RISK_SYNTHESIS_PROMPT
    assert "ParallelEvidence" in RISK_SYNTHESIS_PROMPT or "evidence" in RISK_SYNTHESIS_PROMPT.lower()


def test_event_adapter_produces_serializable_events():
    """Verifies that semantic events serialize cleanly to JSON."""
    event = create_event(
        event_type=EventType.DEPENDENCY_DETECTED,
        stage="EXTRACTION",
        message="Identified low-altitude drone night flight over active traffic",
        data={"element": "Drone Flight", "category": "PERMITS_AND_LEGAL"},
    )
    assert isinstance(event, AgentEvent)
    dumped = event.model_dump_json()
    reloaded = AgentEvent.model_validate_json(dumped)
    assert reloaded.event_type == EventType.DEPENDENCY_DETECTED
    assert reloaded.stage == "EXTRACTION"
    assert "drone" in reloaded.message.lower()


def test_no_secrets_in_events(monkeypatch):
    """Guarantees that sensitive credentials are never leaked in event data payloads."""
    secret_token = "SUPER_SECRET_KEY_NEVER_REVEAL"
    raw_payload = {
        "api_key": secret_token,
        "token": secret_token,
        "auth_secret": secret_token,
        "valid_field": "public_data",
    }
    event = create_event(
        event_type=EventType.PARALLEL_SEARCH_INVOKED,
        stage="RESEARCH",
        message="Calling Parallel Search",
        data=raw_payload,
    )
    event_str = event.model_dump_json()
    assert secret_token not in event_str
    assert "valid_field" in event.data
    assert event.data["valid_field"] == "public_data"


def test_orchestrator_dependency_extraction_structure():
    """Tests that the orchestrator parses scene headings and dependencies into valid Pydantic models."""
    sample_text = """EXT. BROOKLYN BRIDGE - NIGHT
A high-speed tactical drone tracks an armored vehicle across the lower roadway.
Traffic continues below. Rain slicks the pavement."""

    orchestrator = GreenlightOrchestrator()
    breakdown = orchestrator._parse_script_structure(sample_text, "Test Project")

    assert isinstance(breakdown, ScreenplayBreakdown)
    assert len(breakdown.scenes) == 1
    scene = breakdown.scenes[0]
    assert scene.slugline.setting == SettingType.EXT
    assert "BROOKLYN" in scene.slugline.location.upper()
    assert scene.slugline.time_of_day == TimeOfDay.NIGHT
    assert len(scene.dependencies) > 0

    # Ensure at least one drone-related dependency was detected
    dep_elements = [d.element.lower() for d in scene.dependencies]
    assert any("drone" in elem for elem in dep_elements)


def test_orchestrator_risk_evaluation_logic():
    """Tests risk scoring based on retrieved evidence keywords."""
    orchestrator = GreenlightOrchestrator()
    dep = ProductionDependency(
        element="Night drone flight over traffic",
        category=DependencyCategory.PERMITS_AND_LEGAL,
        risk_description="FAA flight over moving vehicles restriction",
    )

    # Test RED assignment on strict waiver / prohibition
    red_evidence = ParallelEvidence(
        query="drone flight over traffic FAA waiver",
        source_title="FAA Commercial Drone Operations",
        source_url="https://faa.gov/part107",
        excerpt="Flights over moving vehicles are strictly prohibited under 14 CFR 107.39 without a formal Part 107 waiver.",
    )
    # Signals are only read from sources that pass jurisdiction and activity
    # binding, so a blocker claim needs a governing source that discusses the
    # activity. A bare ParallelEvidence object no longer counts as evidence.
    red_result = ResearchResult(
        objective="Test",
        sources=[
            SearchSource(
                title="FAA Part 107 Waivers",
                url="https://www.faa.gov/uas/commercial_operators/part_107_waivers",
                excerpts=[
                    "Flight of an unmanned aircraft over moving vehicles is prohibited "
                    "in New York without an approved Part 107 waiver."
                ],
            )
        ],
        key_findings=[],
    )
    juris = resolve_jurisdiction("BROOKLYN BRIDGE")
    assessed_red = orchestrator._evaluate_dependency_risk(dep, red_result, red_evidence, None, juris)
    assert assessed_red.status == ProductionStatus.RED
    assert assessed_red.regulatory_exposure is True
    assert assessed_red.signal_provenance, "a blocker claim must cite the source that produced it"
    assert "BLOCKER" in assessed_red.risk_description or "PROHIBITED" in assessed_red.risk_description.upper()
    assert "waiver" in assessed_red.recommended_action.lower()

    # Test YELLOW assignment on routine advance permit requirements
    yellow_evidence = ParallelEvidence(
        query="filming permit timeline",
        source_title="Municipal Film Commission",
        source_url="https://filmcommission.org/rules",
        excerpt="Standard street filming permits require 30 days advance notice with proof of insurance.",
    )
    yellow_result = ResearchResult(
        objective="Test",
        sources=[
            SearchSource(
                title="NYC Film Permits",
                url="https://www.nyc.gov/site/mome/permits/permits.page",
                excerpts=[
                    "Standard street filming permits in New York City covering drone "
                    "flight near traffic require 30 days advance notice with proof of "
                    "insurance."
                ],
            )
        ],
        key_findings=[],
    )
    assessed_yellow = orchestrator._evaluate_dependency_risk(dep, yellow_result, yellow_evidence, None, juris)
    assert assessed_yellow.status == ProductionStatus.YELLOW
    assert "REVIEW REQUIRED" in assessed_yellow.risk_description


def test_brief_synthesis_model_validation():
    """Verifies that brief synthesis builds a fully validated GreenlightBrief."""
    orchestrator = GreenlightOrchestrator()
    slug = Slugline(
        raw="EXT. BROOKLYN BRIDGE - NIGHT",
        setting=SettingType.EXT,
        location="BROOKLYN BRIDGE",
        time_of_day=TimeOfDay.NIGHT,
    )
    scene = Scene(
        scene_number=1,
        slugline=slug,
        summary="A drone chase sequence.",
        characters=["VANCE"],
    )
    breakdown = ScreenplayBreakdown(
        project_title="Brooklyn Heist",
        screenplay_summary="Nocturnal heist sequence.",
        total_scenes=1,
        scenes=[scene],
    )

    evidence = ParallelEvidence(
        query="NYC UAS permits",
        source_title="NYC MOME Guidelines",
        source_url="https://nyc.gov/mome",
        excerpt="30 day permit requirement.",
    )
    # Status is no longer an input to synthesis: the deterministic scoring
    # engine derives it from the evidence signals below. Passing status=RED
    # without signals would (correctly) score as a GREEN, routine dependency.
    assessed = AssessedDependency(
        element="Night drone flight",
        category="PERMITS_AND_LEGAL",
        status=ProductionStatus.RED,
        risk_description="Strict FAA waiver required.",
        parallel_evidence=evidence,
        recommended_action="Apply for waiver 60 days ahead.",
        scene_number=1,
        regulatory_exposure=True,
        lead_time_days=60,
        confidence=EvidenceConfidence.HIGH,
        jurisdiction_match="EXACT",
        bound_source_count=2,
    )

    brief = orchestrator._synthesize_brief(
        project_title="Brooklyn Heist",
        breakdown=breakdown,
        assessed_dependencies=[assessed],
        all_evidence=[evidence],
    )

    assert isinstance(brief, GreenlightBrief)
    assert brief.scorecard.overall_status == ProductionStatus.RED
    assert brief.scorecard.red_count == 1
    assert "BLOCKED" in brief.scorecard.verdict_headline
    # The published score must be reconstructible from its own audit trail.
    bd = brief.scorecard.score_breakdown
    assert bd is not None
    assert bd.starting_score - sum(c.final_penalty for c in bd.contributions) == bd.raw_total
    assert len(brief.evidence_sources) == 1
    assert brief.evidence_sources[0].source_url == "https://nyc.gov/mome"

    # Validate full JSON serialization and deserialization
    json_data = brief.model_dump_json()
    revalidated = GreenlightBrief.model_validate_json(json_data)
    assert revalidated.project_title == "Brooklyn Heist"
