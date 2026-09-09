"""Deterministic end-to-end scoring for the curated demo scenarios.

The live Parallel Search path returns different prose on different days. That
is fine for the product and fatal for a test: the previous
``test_curated_demo_scenarios_have_distinct_risk_profiles`` asserted three
distinct scores while hitting the network, so it could pass or fail depending
on what the web said that hour.

These tests replay frozen real evidence captured from Parallel, so the whole
pipeline — signal extraction, severity derivation, scoring, hard stops — is
exercised end to end with no network and no flake.

Regenerate the fixture only when the demo scenarios themselves change.
"""

import asyncio
import json
import pathlib

import pytest

import server.agent.greenlight_agent as agent_mod
from server.agent.greenlight_agent import GreenlightOrchestrator
from server.models.brief import ProductionStatus
from server.models.research import ResearchConfidence, ResearchResult, SearchSource
from server.services.sample_library import get_scenario_by_id
from server.services.script_parser import ScriptParser

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "evidence" / "curated_evidence.json"

CURATED = [
    "brooklyn-drone-chase",
    "svalbard-arctic",
    "savannah-pyro",
    "stage-interior-dialogue",
    "los-angeles-controlled-street-dialogue",
]

#: The controlled stage scenario exists to prove the scale reaches GREEN
#: without tuning. Its verdict is not asserted here as a target: only that
#: a controlled production scores materially better than a hazardous one.
CONTROLLED = "stage-interior-dialogue"

#: Scenarios that depict genuinely hazardous locations. The two controlled
#: productions are expected to carry few dependencies -- having little to find
#: is the point of them -- so depth assertions do not apply.
HAZARDOUS = ["brooklyn-drone-chase", "svalbard-arctic", "savannah-pyro"]
LOW_RISK = {"stage-interior-dialogue", "los-angeles-controlled-street-dialogue"}


@pytest.fixture(scope="module")
def frozen_evidence():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def replay(monkeypatch, frozen_evidence):
    """Replaces Parallel Search with a replay of recorded payloads."""

    async def _replay(objective, search_queries, **kwargs):
        record = frozen_evidence.get(objective)
        if record is None:
            return ResearchResult(objective=objective, sources=[], key_findings=[], is_mock=True)
        return ResearchResult(
            objective=objective,
            sources=[
                SearchSource(
                    title=s["title"],
                    url=s["url"],
                    publish_date=s.get("publish_date"),
                    excerpts=s.get("excerpts") or [],
                )
                for s in record["sources"]
            ],
            key_findings=[],
            confidence=ResearchConfidence(record.get("confidence", "HIGH")),
            is_mock=record.get("is_mock", False),
        )

    monkeypatch.setattr(agent_mod, "search_parallel", _replay)
    return _replay


def _run(sample_id):
    return asyncio.run(_run_async(sample_id))


class _SilentRunner:
    """Stands in for the ADK runner.

    The agent turn streams narration events and its output is not consumed by
    the scoring path, so stubbing it keeps these tests genuinely offline and
    fast without changing what is under test.
    """

    async def run_async(self, **kwargs):
        return
        yield  # pragma: no cover - makes this an async generator


async def _run_async(sample_id):
    scenario = get_scenario_by_id(sample_id)
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    orchestrator = GreenlightOrchestrator()
    orchestrator.runner = _SilentRunner()
    async for _ in orchestrator.run_analysis_async(
        scenario.script_text, project_title=scenario.title, breakdown=breakdown
    ):
        pass
    return orchestrator.latest_brief


@pytest.mark.parametrize("sample_id", CURATED)
def test_curated_scenario_is_deterministic(replay, sample_id):
    """The same frozen evidence must always yield the same score."""
    first = _run(sample_id)
    second = _run(sample_id)
    assert first.scorecard.readiness_score == second.scorecard.readiness_score
    assert first.scorecard.overall_status == second.scorecard.overall_status


def test_curated_scenarios_have_distinct_risk_profiles(replay):
    """Judge-facing requirement: the demos must not look identical.

    Deterministic replacement for the live-network version of this check.
    """
    briefs = {}
    for sample_id in CURATED:
        briefs[sample_id] = _run(sample_id)

    scores = {sid: b.scorecard.readiness_score for sid, b in briefs.items()}
    profiles = {
        sid: tuple(sorted((d.hazard_class, d.severity.value) for d in b.assessed_dependencies))
        for sid, b in briefs.items()
    }

    # Distinctness is asserted on the *risk profile*, not on the number.
    # Requiring three different integers would invite tuning the engine to
    # separate scenarios that may legitimately be comparably risky; what must
    # never coincide is the underlying hazard analysis.
    assert len(set(profiles.values())) == len(CURATED), f"risk profiles collapsed: {profiles}"
    assert len(set(scores.values())) >= 2, f"scores collapsed entirely: {scores}"

    for sid, brief in briefs.items():
        assert brief.scorecard.score_breakdown is not None, sid
        assert brief.assessed_dependencies, sid
        assert brief.scenes, sid
        # Deep extraction: a hazardous scene yields more than one dependency.
        # The controlled scenario is exempt by design -- having nothing to find
        # is the point of it.
        if sid not in LOW_RISK:
            assert len(brief.assessed_dependencies) >= 3, (sid, len(brief.assessed_dependencies))


def test_controlled_production_scores_better_than_hazardous_ones(replay):
    """The scale must reach the safe end without anyone tuning it there.

    Asserts a relationship, not a number: a controlled stage interior must
    outscore every hazardous location scenario by a wide margin.
    """
    controlled = _run(CONTROLLED)
    hazardous = [_run(sid) for sid in HAZARDOUS]

    for other in hazardous:
        assert controlled.scorecard.readiness_score > other.scorecard.readiness_score + 20

    # And it must get there through the same pipeline, not a special case.
    assert controlled.scorecard.score_breakdown is not None
    assert controlled.scorecard.score_breakdown.reconstruct() == controlled.scorecard.readiness_score
    assert controlled.assessed_dependencies, "even a safe production is assessed"


def test_decision_spectrum_is_reachable(replay):
    """The full verdict scale occurs naturally in the curated set.

    Asserted on presence, not on which scenario lands where: no scenario is
    tuned toward a band, and a scenario is free to move if its evidence moves.
    """
    statuses = {sid: _run(sid).scorecard.overall_status.value for sid in CURATED}
    for band in ("GREEN", "YELLOW", "RED"):
        assert band in statuses.values(), (band, statuses)


def test_controlled_street_scene_carries_no_blocker(replay):
    """A permitted street shoot must not manufacture a critical hazard.

    Checks the risk profile rather than the score: the scenario exists to show
    a proceed-with-controls outcome arising from ordinary permitting, and its
    number is whatever the engine returns.
    """
    brief = _run("los-angeles-controlled-street-dialogue")
    breakdown = brief.scorecard.score_breakdown

    assert brief.scorecard.red_count == 0
    assert not any(c.severity.value == "CRITICAL" for c in breakdown.contributions)
    assert breakdown.hard_stops == []
    assert breakdown.reconstruct() == brief.scorecard.readiness_score

    # Only ordinary location dependencies, each evidence-backed.
    for dep in brief.assessed_dependencies:
        assert dep.category == "LOCATIONS_AND_ACCESS", dep.element
        assert dep.unverified is False, dep.element
        assert dep.jurisdiction_label and "Los Angeles" in dep.jurisdiction_label


@pytest.mark.parametrize("sample_id", CURATED)
def test_curated_score_is_explainable(replay, sample_id):
    """Every curated score must reconstruct from its own audit trail."""
    brief = _run(sample_id)
    breakdown = brief.scorecard.score_breakdown

    deducted = sum(c.final_penalty for c in breakdown.contributions)
    assert breakdown.starting_score - deducted == breakdown.raw_total
    assert breakdown.final_score == brief.scorecard.readiness_score

    # One explanation line per dependency, plus opener and closer.
    lines = breakdown.explain()
    assert lines[0] == "Starting readiness: 100."
    assert lines[-1] == f"Final readiness: {brief.scorecard.readiness_score}."
    for contribution in breakdown.contributions:
        assert contribution.rationale
        assert any(contribution.element in line for line in lines)


@pytest.mark.parametrize("sample_id", CURATED)
def test_curated_dependencies_are_deduplicated(replay, sample_id):
    """A dependency appears once per production, however many scenes use it."""
    brief = _run(sample_id)
    elements = [d.element for d in brief.assessed_dependencies]
    assert len(elements) == len(set(elements)), f"duplicate dependencies: {elements}"


@pytest.mark.parametrize("sample_id", CURATED)
def test_scene_numbers_are_real(replay, sample_id):
    """Assessed dependencies must reference scenes that actually exist."""
    brief = _run(sample_id)
    valid = {s.scene_number for s in brief.scenes}
    for dep in brief.assessed_dependencies:
        assert dep.scene_numbers, dep.element
        assert set(dep.scene_numbers) <= valid, (dep.element, dep.scene_numbers, valid)


def test_status_follows_the_score_not_the_red_count(replay):
    """Two scenarios can share a RED count and still differ in score."""
    briefs = {sid: _run(sid) for sid in CURATED}
    by_red = {}
    for sid, brief in briefs.items():
        red = brief.scorecard.red_count
        by_red.setdefault(red, []).append(brief.scorecard.readiness_score)

    for red_count, scores in by_red.items():
        if len(scores) > 1:
            assert len(set(scores)) == len(scores), (
                f"{len(scores)} scenarios share red_count={red_count} "
                f"and collapsed to the same score: {scores}"
            )
