"""Stage 1 Validation: Imports, Configuration, and Model Serialization."""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))


def run_validation() -> None:
    print("--- 1. Testing Configuration Import & Defaults ---")
    from server.config import settings
    assert settings.google_cloud_project == "greenlight-ac-2026-lkr", f"Unexpected project: {settings.google_cloud_project}"
    assert settings.google_cloud_location == "us-central1", f"Unexpected location: {settings.google_cloud_location}"
    assert settings.google_genai_use_vertexai is True, "Expected vertexai to be True"
    assert settings.is_vertex_configured is True, "Vertex should be reported as configured"
    assert isinstance(settings.is_parallel_configured, bool), "is_parallel_configured should be bool"
    print(f"[OK] Config successfully loaded: Project={settings.google_cloud_project}, Location={settings.google_cloud_location}")
    print(f"[OK] Parallel Configured: {settings.is_parallel_configured}, Demo Mode: {settings.demo_mode}")

    print("\n--- 2. Testing Screenplay Models Serialization ---")
    from server.models import (
        SettingType,
        TimeOfDay,
        DependencyCategory,
        RiskLevel,
        Slugline,
        Character,
        PhysicalElement,
        ProductionDependency,
        Scene,
        ScreenplayBreakdown,
    )

    slugline = Slugline(
        raw="EXT. BROOKLYN BRIDGE - NIGHT",
        setting=SettingType.EXT,
        location="BROOKLYN BRIDGE",
        time_of_day=TimeOfDay.NIGHT,
    )
    char = Character(
        name="AGENT VANCE",
        role_type="PRINCIPAL",
        description="Rooftop operative",
        is_minor=False,
    )
    elem = PhysicalElement(
        name="FPV Tactical Drone",
        category="VEHICLE",
        description="High-speed quadcopter with carbon blades",
        is_hazardous=True,
    )
    dep = ProductionDependency(
        element="Night drone flight over traffic",
        category=DependencyCategory.PERMITS_AND_LEGAL,
        initial_risk=RiskLevel.RED,
        risk_description="FAA Part 107 restriction over moving vehicles",
        requires_external_research=True,
        research_objective="Verify FAA Part 107.39 waiver requirements for night flight in NYC",
    )
    scene = Scene(
        scene_number=1,
        slugline=slugline,
        summary="A rogue drone intercepts an armored transport on the Brooklyn Bridge.",
        page_count=2.5,
        characters=["AGENT VANCE", "PILOT"],
        props_and_wardrobe=["FPV Tactical Drone", "Encrypted Controller"],
        stunts_and_sfx=["Drone high-speed flyby under cables"],
        environmental_factors=["High crosswinds", "Night lighting"],
        dependencies=[dep],
    )
    breakdown = ScreenplayBreakdown(
        project_title="Greenlight: The Heist",
        author="Agentic Cinema Team",
        screenplay_summary="A high-stakes techno-thriller opening with a nocturnal drone pursuit.",
        total_scenes=1,
        scenes=[scene],
    )

    breakdown_json = breakdown.model_dump_json()
    reloaded_breakdown = ScreenplayBreakdown.model_validate_json(breakdown_json)
    assert reloaded_breakdown.project_title == breakdown.project_title
    assert len(reloaded_breakdown.scenes) == 1
    assert reloaded_breakdown.scenes[0].slugline.location == "BROOKLYN BRIDGE"
    print("[OK] ScreenplayBreakdown successfully instantiated, serialized to JSON, and validated.")

    print("\n--- 3. Testing Research & Parallel Models Serialization ---")
    from server.models import (
        ResearchTask,
        SearchSource,
        ResearchResult,
        ResearchConfidence,
        ParallelSearchResponse,
        ParallelResultItem,
    )

    task = ResearchTask(
        task_id="task_001",
        objective="Verify FAA drone permit regulations for NYC Brooklyn Bridge night flight",
        search_queries=[
            "NYC Mayor Office of Media and Entertainment drone permit",
            "FAA Part 107 night flight filming regulations New York City",
        ],
        category="PERMITS_AND_LEGAL",
        dependency_element="Night drone flight over traffic",
    )
    source = SearchSource(
        title="NYC MOME UAS Permitting Guidelines",
        url="https://www.nyc.gov/site/mome/permits/uas-guidelines.page",
        publish_date="2024-01-15",
        excerpts=["Uncrewed Aircraft Systems (UAS) permits require at least 30 days advance notice."],
        relevance_score=0.98,
    )
    res = ResearchResult(
        search_id="par_search_99812",
        objective=task.objective,
        sources=[source],
        key_findings=["30-day notice strictly required", "DOT and NYPD joint authorization needed"],
        confidence=ResearchConfidence.HIGH,
        is_mock=False,
    )
    res_json = res.model_dump_json()
    reloaded_res = ResearchResult.model_validate_json(res_json)
    assert reloaded_res.search_id == "par_search_99812"
    assert len(reloaded_res.sources) == 1

    parallel_resp = ParallelSearchResponse(
        search_id="par_search_99812",
        results=[
            ParallelResultItem(
                url="https://www.nyc.gov/site/mome/permits/uas-guidelines.page",
                title="NYC MOME UAS Guidelines",
                publish_date="2024-01-15",
                excerpts=["Mandatory 30-day notice for UAS permits."],
            )
        ],
    )
    parallel_json = parallel_resp.model_dump_json()
    reloaded_parallel = ParallelSearchResponse.model_validate_json(parallel_json)
    assert reloaded_parallel.search_id == "par_search_99812"
    print("[OK] ResearchTask, ResearchResult, and ParallelSearchResponse successfully serialized and validated.")

    print("\n--- 4. Testing Greenlight Production Brief Models Serialization ---")
    from server.models import (
        ProductionStatus,
        ParallelEvidence,
        AssessedDependency,
        ExecutiveScorecard,
        GreenlightBrief,
    )

    evidence = ParallelEvidence(
        query="NYC drone filming waiver night FAA Brooklyn Bridge",
        source_title="NYC Mayor's Office of Media and Entertainment - UAS Guidelines",
        source_url="https://www.nyc.gov/site/mome/permits/uas-guidelines.page",
        excerpt="Uncrewed Aircraft Systems (UAS) permits require at least 30 days notice and authorization.",
        publish_date="2024-01-15",
    )
    assessed_dep = AssessedDependency(
        element="Night drone flight over traffic",
        category="PERMITS_AND_LEGAL",
        status=ProductionStatus.RED,
        risk_description="FAA Part 107 prohibits flight over moving vehicles without specific Part 107.39 waiver and NYPD approval.",
        parallel_evidence=evidence,
        recommended_action="File FAA Part 107.39 waiver 60 days in advance or replace exterior bridge flight with a CGI plate shot from a stationary tugboat.",
        scene_number=1,
    )
    scorecard = ExecutiveScorecard(
        overall_status=ProductionStatus.YELLOW,
        readiness_score=78,
        total_scenes=1,
        green_count=0,
        yellow_count=0,
        red_count=1,
        verdict_headline="CONDITIONAL GREENLIGHT -- 1 CRITICAL PERMIT HAZARD",
        budget_impact_estimate="Moderate Legal / VFX Contingency (+12-15%)",
        schedule_impact_estimate="Requires 60-day advance waiver window for FAA review",
    )
    brief = GreenlightBrief(
        project_title="Greenlight: The Heist",
        screenplay_summary="A high-stakes techno-thriller opening with a nocturnal drone pursuit.",
        scorecard=scorecard,
        executive_summary="The production is technically viable with standard studio setups, but Scene 1 carries an acute regulatory obstacle with NYC drone regulations.",
        top_risks=["FAA Part 107.39 waiver lead time exceeds production start"],
        recommended_next_steps=["Immediately submit FAA waiver application or authorize CGI plate substitution"],
        assessed_dependencies=[assessed_dep],
        scenes=[scene],
        evidence_sources=[evidence],
    )

    brief_json = brief.model_dump_json()
    reloaded_brief = GreenlightBrief.model_validate_json(brief_json)
    assert reloaded_brief.scorecard.overall_status == ProductionStatus.YELLOW
    assert reloaded_brief.scorecard.readiness_score == 78
    assert len(reloaded_brief.assessed_dependencies) == 1
    assert reloaded_brief.assessed_dependencies[0].status == ProductionStatus.RED
    assert reloaded_brief.assessed_dependencies[0].parallel_evidence.source_url == evidence.source_url
    print("[OK] ExecutiveScorecard, AssessedDependency, and GreenlightBrief successfully serialized and validated.")

    print("\n==========================================")
    print("STAGE 1 VALIDATION PASSED COMPLETELY! [SUCCESS]")
    print("==========================================")


if __name__ == "__main__":
    run_validation()
