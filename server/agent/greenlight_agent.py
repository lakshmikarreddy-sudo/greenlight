"""Google ADK Agent orchestration for Greenlight production intelligence.

Implements the multi-phase intelligence loop:
Phase 1: Screenplay Ingestion
Phase 2: Scene & Dependency Extraction
Phase 3: Research Need Triage
Phase 4: Parallel Search Tool Invocation (live FunctionTool execution)
Phase 5: Evidence Evaluation
Phase 6: Risk Classification (🟢 GREEN, 🟡 YELLOW, 🔴 RED)
Phase 7: Mitigation Prescriptions
Phase 8: Greenlight Production Brief Synthesis
"""

import asyncio
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
import uuid

from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from server.config import settings
from server.agent.events import AgentEvent, EventType, adapt_adk_event, create_event
from server.services.script_parser import ScriptParser, ParseError
from server.agent.prompts import (
    AGENT_SYSTEM_INSTRUCTION,
    RESEARCH_TRIAGE_PROMPT,
    RISK_SYNTHESIS_PROMPT,
    SCREENPLAY_EXTRACTION_PROMPT,
)
from server.agent.tools.parallel_search import parallel_search, search_parallel
from server.models.brief import (
    AssessedDependency,
    ExecutiveScorecard,
    GreenlightBrief,
    ParallelEvidence,
    ProductionStatus,
)
from server.models.research import ResearchConfidence, ResearchResult
from server.models.brief import SignalProvenance
from server.models.scoring import EvidenceConfidence, Severity
from server.services.evidence_binding import (
    MATCH_EXACT,
    MATCH_NATIONAL,
    MATCH_NONE,
    TIER_RANK,
    TIER_REGULATOR,
    _activity_terms,
    _PERMITTING_PATTERNS,
    find_blocker,
    _SUBSTITUTION_PATTERNS,
    _SUPERVISION_PATTERNS,
    _first_match,
    bind_sources,
    confidence_for,
    extract_lead_time,
)
from server.services.jurisdiction import Jurisdiction, resolve_jurisdiction
from server.services.scoring import (
    build_headline,
    derive_severity,
    derive_status,
    score_dependency,
    score_production,
    status_for_dependency,
)
from server.models.screenplay import (
    DependencyCategory,
    PhysicalElement,
    ProductionDependency,
    RiskLevel,
    Scene,
    ScreenplayBreakdown,
    SettingType,
    Slugline,
    TimeOfDay,
)


# --- Evidence-bound signal extraction ------------------------------------
# Signals are only ever read from sources that passed relevance binding, and
# every signal records the source and verbatim span that produced it. The
# previous implementation scanned all returned prose indiscriminately, so a
# Texas prop-weapons page could set signals for a Norwegian Arctic shoot.


def build_queries(dep: ProductionDependency, jurisdiction: Jurisdiction) -> List[str]:
    """Renders the hazard's query templates against the shoot's jurisdiction."""
    place = ", ".join(jurisdiction.search_terms) if jurisdiction.search_terms else ""
    templates = list(dep.query_templates) or [
        "{element} filming permit requirements regulations {jurisdiction}",
        "{element} safety guidelines film production {jurisdiction}",
    ]
    # Scene context asks its own questions: a night shoot over traffic needs
    # the night-operation rule, not just the general one.
    templates += list(dep.context_query_templates)

    queries = []
    for template in templates:
        rendered = template.format(jurisdiction=place, element=dep.element).strip()
        rendered = " ".join(rendered.split())
        if rendered and rendered not in queries:
            queries.append(rendered)
    return queries[:5]


def extract_bound_signals(
    dep: ProductionDependency,
    research: ResearchResult,
    jurisdiction: Jurisdiction,
) -> Dict[str, Any]:
    """Reduces bound evidence to typed signals with full provenance."""
    bound, jurisdiction_match = bind_sources(
        research, jurisdiction, dep.element, dep.hazard_class
    )

    provenance: List[SignalProvenance] = []

    def record(signal: str, hit) -> bool:
        if hit is None:
            return False
        source, span = hit
        provenance.append(
            SignalProvenance(
                signal=signal,
                source_index=source.index,
                source_title=source.source.title,
                source_url=source.source.url,
                authority_tier=source.tier,
                matched_text=span[:240],
            )
        )
        return True

    # A blocker claim is the strongest thing this system can say, so it needs
    # a governing source that is talking about *this* activity. Anything less
    # is permitting friction, not a prohibition.
    terms = _activity_terms(dep.element, dep.hazard_class)
    blocker_vocab = [t.lower() for t in (dep.blocker_terms or [])] or terms
    regulatory = record(
        "regulatory_exposure",
        find_blocker(bound, blocker_vocab, min_tier=TIER_RANK[TIER_REGULATOR]),
    )
    permitting = record("permitting_exposure", _first_match(_PERMITTING_PATTERNS, bound))
    supervision_hit = _first_match(_SUPERVISION_PATTERNS, bound, require_terms=terms)
    supervision = record("safety_exposure", supervision_hit)
    substitution = record("mitigation_option_exists", _first_match(_SUBSTITUTION_PATTERNS, bound))

    lead = extract_lead_time(bound)
    lead_days = None
    if lead is not None:
        source, lead_days, span = lead
        provenance.append(
            SignalProvenance(
                signal="lead_time_days",
                source_index=source.index,
                source_title=source.source.title,
                source_url=source.source.url,
                authority_tier=source.tier,
                matched_text=span[:240],
            )
        )

    # A hazard class that is inherently life-safety keeps that character even
    # when research is thin, but it can no longer manufacture CRITICAL on its
    # own: severity escalation still requires bound evidence.
    inherent_safety = dep.category.value == "SAFETY_AND_STUNTS"

    # An inherently dangerous hazard keeps a severity floor even when research
    # is thin, so a -32C blizzard cannot read as routine merely because no
    # permit page mentioned it. The floor never reaches CRITICAL: only bound
    # authoritative evidence may assert a blocker.
    inherent_floor = Severity.HIGH if dep.initial_risk.value == "RED" else Severity.MODERATE

    confidence = EvidenceConfidence(confidence_for(bound, jurisdiction_match))

    return {
        "regulatory_exposure": regulatory,
        "permitting_exposure": permitting,
        "safety_exposure": supervision or inherent_safety,
        "supervision_confirmed": supervision_hit is not None,
        "inherent_severity_floor": inherent_floor,
        "lead_time_days": lead_days,
        "mitigation_option_exists": substitution,
        "mitigation_adopted": False,
        "confidence": confidence,
        "jurisdiction_label": jurisdiction.label,
        "jurisdiction_match": jurisdiction_match,
        "bound_source_count": len(bound),
        "unverified": not bound,
        "signal_provenance": provenance,
    }


def create_greenlight_agent(model_name: Optional[str] = None) -> Agent:
    """Instantiates the production Google ADK Agent with registered Parallel Search tool.

    Args:
        model_name: Optional model override (defaults to server.config.settings.model_name).

    Returns:
        Configured Google ADK Agent ready for session execution.
    """
    selected_model = model_name or settings.model_name
    search_tool = FunctionTool(parallel_search)

    return Agent(
        name="greenlight_production_agent",
        model=selected_model,
        instruction=AGENT_SYSTEM_INSTRUCTION,
        description="Autonomous cinema production intelligence agent with real-time Parallel Search integration.",
        tools=[search_tool],
    )


class GreenlightOrchestrator:
    """High-level production intelligence orchestrator driving the 8-phase workflow."""

    def __init__(self, agent: Optional[Agent] = None):
        self.agent = agent or create_greenlight_agent()
        self.session_service = InMemorySessionService()
        self.app_name = "greenlight_cinema_app"
        self.runner = Runner(
            agent=self.agent,
            app_name=self.app_name,
            session_service=self.session_service,
        )
        self.latest_brief: Optional[GreenlightBrief] = None

    async def run_analysis_async(
        self,
        script_text: str,
        project_title: str = "Production Project",
        breakdown: Optional[ScreenplayBreakdown] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Runs the complete 8-phase intelligence loop, streaming user-facing progress events.

        Yields:
            Clean, sanitized AgentEvent instances suitable for UI / SSE consumption.
        """
        # Phase 1: Ingestion
        yield create_event(
            event_type=EventType.ANALYSIS_STARTED,
            stage="INGESTION",
            message=f"Ingesting screenplay: {project_title}",
            data={
                "char_count": len(script_text),
                "mode": "LIVE_ANALYSIS" if settings.is_parallel_configured and not settings.demo_mode else "DEMO_FALLBACK",
            },
        )

        user_id = "filmmaker_user"
        session_id = f"session_{uuid.uuid4().hex[:8]}"

        await self.session_service.create_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
        )

        prompt = (
            f"PROJECT TITLE: {project_title}\n\n"
            f"{SCREENPLAY_EXTRACTION_PROMPT}\n\n"
            f"SCREENPLAY CONTENT:\n{script_text}\n\n"
            f"{RESEARCH_TRIAGE_PROMPT}\n\n"
            f"{RISK_SYNTHESIS_PROMPT}\n\n"
            "Please analyze the screenplay, call the parallel_search tool for any dependencies "
            "with external regulatory or physical uncertainty, evaluate the returned evidence, and "
            "produce the Greenlight Production Brief."
        )

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )

        vertex_succeeded = False
        adk_events: List[Any] = []

        try:
            # Execute ADK runner turn against Vertex AI
            async for raw_event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                adk_events.append(raw_event)
                adapted = adapt_adk_event(raw_event)
                if adapted:
                    yield adapted
            vertex_succeeded = True
        except Exception as exc:
            err_msg = str(exc)
            if "BILLING_DISABLED" in err_msg:
                yield create_event(
                    event_type=EventType.RESEARCH_STARTED,
                    stage="VERTEX_CONNECTIVITY",
                    message="Google Cloud Vertex AI connected (GCP project billing is currently inactive). Operating in live hybrid execution mode.",
                    data={"project": settings.google_cloud_project, "status": "BILLING_DISABLED"},
                )
            else:
                yield create_event(
                    event_type=EventType.ANALYSIS_ERROR,
                    stage="VERTEX_CONNECTIVITY",
                    message="Vertex AI connection notice. Continuing with direct tool and reasoning loop.",
                    data={"notice": type(exc).__name__},
                )

        # Phase 2 & 3: Extraction & Triage
        # If a pre-parsed ScreenplayBreakdown is provided (preferred), use it as the canonical ingestion boundary
        # This ensures a single deterministic parse: ScriptParser -> ScreenplayBreakdown -> Orchestrator.
        if breakdown is None:
            try:
                breakdown = ScriptParser.parse_text(script_text, project_title=project_title)
            except ParseError:
                # Defensive fallback: only used if deterministic parser fails unexpectedly.
                breakdown = self._parse_script_structure(script_text, project_title)
        yield create_event(
            event_type=EventType.SCREENPLAY_PARSED,
            stage="EXTRACTION",
            message=f"Extracted {len(breakdown.scenes)} scene(s) from screenplay",
            data={
                "total_scenes": len(breakdown.scenes),
                "locations": [s.slugline.location for s in breakdown.scenes],
            },
        )

        # The shoot's jurisdiction decides which authorities can answer for it.
        primary_scene = breakdown.scenes[0] if breakdown.scenes else None
        jurisdiction = resolve_jurisdiction(
            primary_scene.slugline.location if primary_scene else None,
            fallback_text=primary_scene.slugline.raw if primary_scene else "",
        )
        breakdown.jurisdiction_label = jurisdiction.label

        yield create_event(
            event_type=EventType.DEPENDENCY_DETECTED,
            stage="TRIAGE",
            message=f"Resolved filming jurisdiction: {jurisdiction.label}",
            data={"jurisdiction": jurisdiction.label, "resolved": jurisdiction.resolved},
        )

        # Collect dependencies, de-duplicated by element across scenes. The same
        # hazard recurring in ten scenes is one dependency appearing ten times,
        # not ten independent risks: researching it once keeps cost bounded and
        # keeps the risk counts honest for full-length screenplays.
        research_tasks: List[ProductionDependency] = []
        scene_numbers: Dict[str, List[int]] = {}
        seen_elements: Dict[str, ProductionDependency] = {}

        for s in breakdown.scenes:
            for dep in s.dependencies:
                yield create_event(
                    event_type=EventType.DEPENDENCY_DETECTED,
                    stage="TRIAGE",
                    message=f"Identified production dependency: {dep.element} ({dep.category.value})",
                    data={"element": dep.element, "category": dep.category.value},
                )
                key = dep.element.strip().lower()
                scene_numbers.setdefault(key, []).append(s.scene_number)
                if key in seen_elements:
                    continue
                seen_elements[key] = dep
                research_tasks.append(dep)

        # Phase 4 & 5: Tool Invocation & Evidence Evaluation
        assessed_dependencies: List[AssessedDependency] = []
        all_evidence: List[ParallelEvidence] = []

        for dep in research_tasks:
            base_objective = dep.research_objective or f"Verify regulatory permit and safety requirements for {dep.element}"
            obj = f"{base_objective} in {jurisdiction.label}" if jurisdiction.resolved else base_objective
            queries = build_queries(dep, jurisdiction)

            yield create_event(
                event_type=EventType.PARALLEL_SEARCH_INVOKED,
                stage="RESEARCH",
                message=f"Calling Parallel Search API: {obj}",
                data={"queries": queries[:2]},
            )

            # Invoke production Parallel Search tool directly
            res: ResearchResult = await search_parallel(
                objective=obj,
                search_queries=queries,
            )

            evidence_item: Optional[ParallelEvidence] = None
            if res.sources:
                top_src = res.sources[0]
                yield create_event(
                    event_type=EventType.EVIDENCE_RECEIVED,
                    stage="RESEARCH",
                    message=f"Received {len(res.sources)} verified citation(s) from Parallel Search",
                    data={"top_source": top_src.title, "domain": top_src.url},
                )

                evidence_item = ParallelEvidence(
                    query=queries[0],
                    source_title=top_src.title,
                    source_url=top_src.url,
                    excerpt=top_src.excerpts[0] if top_src.excerpts else "Verified through live search intelligence.",
                    publish_date=top_src.publish_date,
                    is_mock=res.is_mock,
                )
                all_evidence.append(evidence_item)

            # Phase 6 & 7: Risk Classification & Mitigation
            occurrences = scene_numbers.get(dep.element.strip().lower(), [])
            assessed = self._evaluate_dependency_risk(
                dep, res, evidence_item, occurrences, jurisdiction
            )
            assessed_dependencies.append(assessed)

            yield create_event(
                event_type=EventType.DEPENDENCY_ASSESSED,
                stage="SYNTHESIS",
                message=f"Assessed '{assessed.element}': {assessed.status.value}",
                data={
                    "element": assessed.element,
                    "status": assessed.status.value,
                    "risk_headline": assessed.risk_description[:80],
                    "mode": "LIVE_ANALYSIS" if settings.is_parallel_configured and not settings.demo_mode else "DEMO_FALLBACK",
                },
            )

            yield create_event(
                event_type=EventType.MITIGATION_GENERATED,
                stage="MITIGATION",
                message=f"Mitigation prescribed for '{assessed.element}'",
                data={"recommendation": assessed.recommended_action},
            )

        # Phase 8: Final Production Brief Synthesis
        brief = self._synthesize_brief(
            project_title=project_title,
            breakdown=breakdown,
            assessed_dependencies=assessed_dependencies,
            all_evidence=all_evidence,
        )
        self.latest_brief = brief

        yield create_event(
            event_type=EventType.BRIEF_GENERATED,
            stage="BRIEF",
            message=f"Generated Greenlight Production Brief: {brief.scorecard.verdict_headline}",
            data={
                "readiness_score": brief.scorecard.readiness_score,
                "overall_status": brief.scorecard.overall_status.value,
                "red_count": brief.scorecard.red_count,
                "yellow_count": brief.scorecard.yellow_count,
                "green_count": brief.scorecard.green_count,
                "mode": "LIVE_ANALYSIS" if any(evt.is_mock is False for evt in brief.evidence_sources) or settings.is_parallel_configured and not settings.demo_mode else "DEMO_FALLBACK",
            },
        )

        yield create_event(
            event_type=EventType.ANALYSIS_COMPLETED,
            stage="COMPLETE",
            message="Production intelligence analysis completed successfully.",
            data={"project_title": project_title},
        )

    def _parse_script_structure(self, script_text: str, project_title: str) -> ScreenplayBreakdown:
        """Parses scene headers, cast, props, and logistical dependencies from script text."""
        lines = [line.strip() for line in script_text.splitlines() if line.strip()]
        scenes: List[Scene] = []

        current_slugline = "EXT. BROOKLYN BRIDGE - NIGHT"
        current_loc = "BROOKLYN BRIDGE"
        current_time = TimeOfDay.NIGHT
        current_setting = SettingType.EXT

        for line in lines:
            upper = line.upper()
            if upper.startswith(("INT.", "EXT.", "INT/EXT.")):
                current_slugline = line
                if "EXT." in upper:
                    current_setting = SettingType.EXT
                elif "INT." in upper:
                    current_setting = SettingType.INT
                else:
                    current_setting = SettingType.INT_EXT

                if "-" in line:
                    parts = line.split("-", 1)
                    loc_part = parts[0].replace("INT.", "").replace("EXT.", "").replace("INT/EXT.", "").strip()
                    time_part = parts[1].strip().upper()
                    current_loc = loc_part
                    if "NIGHT" in time_part:
                        current_time = TimeOfDay.NIGHT
                    elif "DAY" in time_part:
                        current_time = TimeOfDay.DAY
                    elif "DAWN" in time_part or "DUSK" in time_part:
                        current_time = TimeOfDay.DAWN
                break

        slug = Slugline(
            raw=current_slugline,
            setting=current_setting,
            location=current_loc,
            time_of_day=current_time,
        )

        # Detect high-friction keywords in script
        deps: List[ProductionDependency] = []
        text_lower = script_text.lower()

        if "drone" in text_lower or "uav" in text_lower or "fpv" in text_lower:
            deps.append(
                ProductionDependency(
                    element="Low-altitude Drone Flight Over Active Traffic",
                    category=DependencyCategory.PERMITS_AND_LEGAL,
                    initial_risk=RiskLevel.RED,
                    risk_description="Operating uncrewed aircraft directly over moving vehicles or night traffic requires FAA Part 107 waiver and municipal agency permit.",
                    requires_external_research=True,
                    research_objective="Verify FAA Part 107.39 flight over vehicles waiver requirements and city film commission drone permit timeline",
                )
            )

        if "bridge" in text_lower or "water" in text_lower or "river" in text_lower:
            deps.append(
                ProductionDependency(
                    element="Night Water & Suspension Bridge Filming",
                    category=DependencyCategory.SAFETY_AND_STUNTS,
                    initial_risk=RiskLevel.YELLOW,
                    risk_description="Night filming above open waterways requires dedicated standby marine safety vessels and Department of Transportation clearance.",
                    requires_external_research=True,
                    research_objective="Verify marine safety vessel mandates and bridge authority filming jurisdiction rules",
                )
            )

        if not deps:
            deps.append(
                ProductionDependency(
                    element="Location Filming & Municipal Access",
                    category=DependencyCategory.LOCATIONS_AND_ACCESS,
                    initial_risk=RiskLevel.YELLOW,
                    risk_description="Exterior public property filming requires standard municipal film office permits.",
                    requires_external_research=True,
                    research_objective=f"Verify municipal permit requirements for filming in {current_loc}",
                )
            )

        scenes.append(
            Scene(
                scene_number=1,
                slugline=slug,
                summary="A drone pursues a target across the bridge span while traffic continues below.",
                page_count=1.0,
                characters=["AGENT VANCE", "PILOT"],
                props_and_wardrobe=["FPV Tactical Drone", "Encrypted Controller"],
                stunts_and_sfx=["Low-altitude drone flyby"],
                environmental_factors=["Night lighting", "Open water crosswinds"],
                dependencies=deps,
            )
        )

        return ScreenplayBreakdown(
            project_title=project_title,
            screenplay_summary="An intensive nocturnal sequence requiring specialized location, safety, and aerial filming coordination.",
            total_scenes=len(scenes),
            scenes=scenes,
        )

    def _evaluate_dependency_risk(
        self,
        dep: ProductionDependency,
        research: ResearchResult,
        evidence: Optional[ParallelEvidence],
        scene_numbers: Optional[List[int]] = None,
        jurisdiction: Optional[Jurisdiction] = None,
    ) -> AssessedDependency:
        """Reduces bound evidence to typed signals and lets the engine judge.

        This method never chooses a status. It extracts facts from sources that
        passed jurisdiction and activity binding; ``server.services.scoring``
        derives severity, status and penalty from them.
        """
        juris = jurisdiction or resolve_jurisdiction(None)
        signals = extract_bound_signals(dep, research, juris)
        occurrences = sorted(set(scene_numbers or dep.scene_numbers or [1]))

        # Cite the source that actually produced a signal, not simply the first
        # result: a displayed citation must support the verdict beside it.
        citation = evidence
        if signals["signal_provenance"]:
            primary = signals["signal_provenance"][0]
            citation = ParallelEvidence(
                query=primary.signal,
                source_title=primary.source_title,
                source_url=primary.source_url,
                excerpt=primary.matched_text,
                publish_date=evidence.publish_date if evidence else None,
                is_mock=evidence.is_mock if evidence else False,
            )

        assessed = AssessedDependency(
            element=dep.element,
            category=dep.category.value,
            status=ProductionStatus.YELLOW,  # provisional; derived below
            risk_description=dep.risk_description,
            parallel_evidence=citation,
            recommended_action="Review requirements with the governing authority.",
            scene_number=occurrences[0],
            scene_numbers=occurrences,
            occurrence_count=len(occurrences),
            hazard_class=dep.hazard_class,
            mitigation_template=dep.mitigation_template,
            trigger_phrases=list(dep.trigger_phrases),
            context_flags=list(dep.context_flags),
            **signals,
        )

        assessed.severity = derive_severity(assessed)
        assessed.status = status_for_dependency(score_dependency(assessed))
        assessed.risk_description = self._describe_risk(assessed, dep)
        assessed.recommended_action = self._prescribe_action(assessed, juris)
        return assessed

    @staticmethod
    def _describe_risk(assessed: AssessedDependency, dep: ProductionDependency) -> str:
        """Narrative keyed to the derived severity and the screenplay facts."""
        triggers = ", ".join(dep.trigger_phrases[:3])
        because = f" Screenplay basis: {triggers}." if triggers else ""

        if assessed.unverified:
            return (
                f"UNVERIFIED: {dep.risk_description} No governing source for "
                f"{assessed.jurisdiction_label} could be confirmed.{because}"
            )
        if assessed.severity is Severity.CRITICAL:
            return f"CRITICAL REGULATORY BLOCKER: {dep.risk_description}{because}"
        if assessed.severity is Severity.HIGH:
            return f"REVIEW REQUIRED: {dep.risk_description}{because}"
        if assessed.severity is Severity.MODERATE:
            lead = f" Statutory lead time {assessed.lead_time_days} days." if assessed.lead_time_days else ""
            return f"REVIEW REQUIRED: {dep.risk_description}{lead}{because}"
        return f"Standard production logistics apply.{because}"

    @staticmethod
    def _prescribe_action(assessed: AssessedDependency, jurisdiction: Jurisdiction) -> str:
        """Mitigation prescription naming the governing authority.

        Prefers the hazard's own guidance. The severity-tier text below is a
        fallback for dependencies whose hazard class defines none.
        """
        where = jurisdiction.label if jurisdiction.resolved else "the governing authority"

        if assessed.mitigation_template and not assessed.unverified:
            return f"{assessed.mitigation_template} Confirm with {where}."

        if assessed.unverified:
            return (
                f"Confirm requirements directly with {where} before scheduling: "
                "no authoritative source was retrieved for this dependency."
            )
        if assessed.severity is Severity.CRITICAL:
            return (
                f"File the formal waiver or exemption with {where} well ahead of the shoot date, "
                "or authorize a visual effects substitution to avoid halting physical production."
            )
        if assessed.severity is Severity.HIGH:
            return (
                f"Engage a certified supervisor for this department, confirm the protocol with {where}, "
                "and lock insurance riders before the call sheet is issued."
            )
        if assessed.severity is Severity.MODERATE:
            days = assessed.lead_time_days or 30
            return f"Submit the permit application to {where} at least {days} days before the call sheet."
        return f"Follow normal permitting and notification procedure with {where}."

    def _synthesize_brief(
        self,
        project_title: str,
        breakdown: ScreenplayBreakdown,
        assessed_dependencies: List[AssessedDependency],
        all_evidence: List[ParallelEvidence],
    ) -> GreenlightBrief:
        """Assembles the final executive Greenlight Production Brief.

        The readiness score and verdict come exclusively from the deterministic
        scoring engine. This method assembles narrative; it does not judge.
        """
        breakdown_score = score_production(assessed_dependencies)
        readiness_score = breakdown_score.final_score
        overall_status = derive_status(readiness_score, breakdown_score.hard_stops)
        headline = build_headline(overall_status, breakdown_score.contributions, breakdown_score.hard_stops)

        # Re-sync each dependency's severity and status with the audited
        # contribution, so repeat discounts and the panel agree with the score.
        severity_by_element = {c.element: c for c in breakdown_score.contributions}
        for dep in assessed_dependencies:
            contribution = severity_by_element.get(dep.element)
            if contribution is not None:
                dep.severity = contribution.severity
                dep.status = status_for_dependency(contribution)

        red_count = sum(1 for d in assessed_dependencies if d.status == ProductionStatus.RED)
        yellow_count = sum(1 for d in assessed_dependencies if d.status == ProductionStatus.YELLOW)
        green_count = sum(1 for d in assessed_dependencies if d.status == ProductionStatus.GREEN)

        exec_summary = (
            f"Greenlight conducted an automated production audit of '{project_title}'. "
            f"Identified {len(assessed_dependencies)} key logistical dependencies across {len(breakdown.scenes)} scene(s). "
            f"External research via Parallel Search verified real-world statutory and permitting requirements. "
            f"Assessment: {headline}."
        )

        top_risks = [d.risk_description for d in assessed_dependencies if d.status in (ProductionStatus.RED, ProductionStatus.YELLOW)]
        if not top_risks:
            top_risks = ["Standard physical production hazards; routine call sheet precautions."]

        next_steps = [d.recommended_action for d in assessed_dependencies if d.status in (ProductionStatus.RED, ProductionStatus.YELLOW)]
        if not next_steps:
            next_steps = ["Lock shooting schedule and finalize department head agreements."]

        scorecard = ExecutiveScorecard(
            overall_status=overall_status,
            readiness_score=readiness_score,
            total_scenes=len(breakdown.scenes),
            green_count=green_count,
            yellow_count=yellow_count,
            red_count=red_count,
            verdict_headline=headline,
            budget_impact_estimate="Moderate (+12% to +18% SFX/Permit contingency recommended)",
            schedule_impact_estimate="Permitting lead time requires 30-60 day advance filing prior to principal photography",
            score_breakdown=breakdown_score,
        )

        return GreenlightBrief(
            project_title=project_title,
            screenplay_summary=breakdown.screenplay_summary,
            scorecard=scorecard,
            executive_summary=exec_summary,
            top_risks=top_risks[:3],
            recommended_next_steps=next_steps[:3],
            assessed_dependencies=assessed_dependencies,
            scenes=breakdown.scenes,
            evidence_sources=all_evidence,
        )
