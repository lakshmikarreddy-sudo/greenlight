"""Final Greenlight Production Brief schemas reflecting the product specification."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from server.models.screenplay import Scene
from server.models.scoring import EvidenceConfidence, ScoreBreakdown, Severity


class ProductionStatus(str, Enum):
    """Three-tier production status classification."""
    GREEN = "GREEN"      # Low concern / routine protocol / Greenlight
    YELLOW = "YELLOW"    # Review required / conditional friction / Conditional
    RED = "RED"          # Significant production risk / blocker / Blocked


class ParallelEvidence(BaseModel):
    """External citation and passage excerpt retrieved from Parallel Search."""
    query: str = Field(..., description="The search query that surfaced this evidence")
    source_title: str = Field(..., description="Title of the source publication or authority")
    source_url: str = Field(..., description="Clickable URL to the authoritative source")
    excerpt: str = Field(..., description="Relevant factual passage proving regulatory or physical constraint")
    publish_date: Optional[str] = Field(default=None, description="Publication date if available")
    is_mock: bool = Field(default=False, description="True when evidence came from the built-in demo fixture instead of live external research")


class SignalProvenance(BaseModel):
    """Which evidence produced a given signal.

    Without this a brief can display a citation beside a verdict that a
    different, unshown source actually produced.
    """
    signal: str = Field(..., description="Signal name, e.g. regulatory_exposure")
    source_index: int = Field(..., description="Index into the dependency's bound sources")
    source_title: str = Field(..., description="Title of the source that produced the signal")
    source_url: str = Field(..., description="URL of the source that produced the signal")
    authority_tier: str = Field(..., description="Authority tier of that source")
    matched_text: str = Field(..., description="Verbatim span from the source that triggered the signal")


class AssessedDependency(BaseModel):
    """A production dependency with risk scoring, Parallel evidence, and recommended mitigation."""
    element: str = Field(..., description="Name of the production dependency")
    category: str = Field(..., description="Category: PERMITS_AND_LEGAL, SAFETY_AND_STUNTS, WEATHER, etc.")
    status: ProductionStatus = Field(..., description="🟢 GREEN, 🟡 YELLOW, or 🔴 RED")
    risk_description: str = Field(..., description="Detailed explanation of the production risk or hurdle")
    parallel_evidence: Optional[ParallelEvidence] = Field(default=None, description="Parallel Search ground truth evidence")
    recommended_action: str = Field(..., description="Specific, actionable filmmaker mitigation advice")
    scene_number: Optional[int] = Field(default=None, description="Optional scene reference number")

    # --- Deterministic scoring signals -------------------------------------
    # Extracted from evidence as typed facts, never as a verdict. The scoring
    # engine derives severity and penalties from these; nothing else may.
    severity: Severity = Field(default=Severity.MODERATE, description="Derived risk magnitude driving the readiness deduction")
    regulatory_exposure: bool = Field(default=False, description="Evidence indicates statutory prohibition or a waiver regime")
    permitting_exposure: bool = Field(default=False, description="Evidence mandates permits, licensing or insurance without a stated lead time")
    safety_exposure: bool = Field(default=False, description="Life-safety operation requiring certified supervision")
    lead_time_days: Optional[int] = Field(default=None, description="Statutory lead time in days, when evidence states one")
    mitigation_available: bool = Field(default=False, description="A documented substitution (e.g. CGI plate) exists")
    confidence: EvidenceConfidence = Field(default=EvidenceConfidence.MEDIUM, description="Confidence in the supporting evidence")
    occurrence_count: int = Field(default=1, ge=1, description="Scenes this dependency was detected in, after de-duplication")
    scene_numbers: List[int] = Field(default_factory=list, description="Every scene this dependency appears in")

    # --- Extraction and evidence provenance (C1-C4) -----------------------
    hazard_class: Optional[str] = Field(default=None, description="Standard hazard class this dependency belongs to")
    trigger_phrases: List[str] = Field(default_factory=list, description="Screenplay phrases that produced this dependency")
    context_flags: List[str] = Field(default_factory=list, description="Scene facts aggravating the hazard, e.g. night_work")
    jurisdiction_label: Optional[str] = Field(default=None, description="Jurisdiction this dependency was researched against")
    jurisdiction_match: str = Field(default="NONE", description="EXACT, NATIONAL or NONE: how well the evidence matched the shoot's jurisdiction")
    bound_source_count: int = Field(default=0, ge=0, description="Sources that passed relevance binding and were allowed to contribute signals")
    unverified: bool = Field(default=False, description="True when no bound evidence supports this dependency")
    supervision_confirmed: bool = Field(default=False, description="Evidence confirmed a named supervision or certification regime")
    mitigation_template: Optional[str] = Field(default=None, description="Hazard-specific mitigation guidance, when the hazard class defines one")
    inherent_severity_floor: Severity = Field(default=Severity.LOW, description="Severity this hazard class carries before evidence; never reaches CRITICAL")
    mitigation_option_exists: bool = Field(default=False, description="Evidence mentions a substitution option; informational only")
    mitigation_adopted: bool = Field(default=False, description="Production has confirmed adopting a substitution; reduces residual only")
    signal_provenance: List["SignalProvenance"] = Field(default_factory=list, description="Which source and phrase produced each signal")


class ExecutiveScorecard(BaseModel):
    """High-level metrics and viability verdict for production executives."""
    overall_status: ProductionStatus = Field(..., description="Overall greenlight verdict")
    readiness_score: int = Field(..., ge=0, le=100, description="Readiness score from 0 (impossible) to 100 (turnkey)")
    total_scenes: int = Field(..., ge=0, description="Total scenes analyzed")
    green_count: int = Field(default=0, ge=0, description="Number of low-concern elements")
    yellow_count: int = Field(default=0, ge=0, description="Number of review-required elements")
    red_count: int = Field(default=0, ge=0, description="Number of critical production blockers")
    verdict_headline: str = Field(..., description="Display headline, e.g. 'CONDITIONAL GREENLIGHT — 3 PERMIT HAZARDS'")
    budget_impact_estimate: str = Field(..., description="High-level financial implication estimate")
    schedule_impact_estimate: str = Field(..., description="Estimated timeline friction or lead-time requirement")
    score_breakdown: Optional[ScoreBreakdown] = Field(default=None, description="Line-by-line audit of how the readiness score was reached")


class GreenlightBrief(BaseModel):
    """The comprehensive Greenlight Production Brief delivered to filmmakers."""
    project_title: str = Field(..., description="Project / screenplay title")
    screenplay_summary: str = Field(..., description="Executive narrative summary of the script")
    scorecard: ExecutiveScorecard = Field(..., description="Executive scorecard and metrics")
    executive_summary: str = Field(..., description="In-depth executive assessment narrative")
    top_risks: List[str] = Field(default_factory=list, description="Bullet points of the most urgent threats to production")
    recommended_next_steps: List[str] = Field(default_factory=list, description="Top actionable priorities for the filmmaker")
    assessed_dependencies: List[AssessedDependency] = Field(default_factory=list, description="Full matrix of assessed dependencies")
    scenes: List[Scene] = Field(default_factory=list, description="Scene-by-scene breakdown detail")
    evidence_sources: List[ParallelEvidence] = Field(default_factory=list, description="Complete bibliography of cited Parallel sources")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of brief generation"
    )
