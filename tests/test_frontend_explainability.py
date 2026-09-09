"""Tests for the readiness explainability surface.

Two layers:

  * The *logic* of ``server/static/js/explain.js`` is executed for real. That
    module is deliberately pure ESM with no DOM access, so Node can import it
    directly and we can assert on the view model it builds from a genuine
    brief. No browser and no npm dependency required.
  * The *wiring* in index.html and app.js is checked structurally, in the same
    style as the existing frontend contract tests.

The behaviour that matters most here: a classification backed by a governing
source and one applied from a hazard-class baseline must never be presented
alike. Brooklyn's Work at Height is the live example -- HIGH with no evidence.
"""

import asyncio
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

import server.agent.greenlight_agent as agent_mod
from server.agent.greenlight_agent import GreenlightOrchestrator
from server.models.research import ResearchConfidence, ResearchResult, SearchSource
from server.services.sample_library import get_scenario_by_id
from server.services.script_parser import ScriptParser

STATIC = pathlib.Path(__file__).resolve().parent.parent / "server" / "static"
EXPLAIN_JS = STATIC / "js" / "explain.js"
APP_JS = STATIC / "js" / "app.js"
INDEX = STATIC / "index.html"
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "evidence" / "curated_evidence.json"

CURATED = [
    "brooklyn-drone-chase",
    "svalbard-arctic",
    "savannah-pyro",
    "stage-interior-dialogue",
    "los-angeles-controlled-street-dialogue",
]

NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


# --------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def frozen():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _SilentRunner:
    async def run_async(self, **kwargs):
        return
        yield  # pragma: no cover


def _brief(sample_id, frozen):
    """Runs the real pipeline offline and returns the brief as the UI sees it."""

    async def replay(objective, search_queries, **kwargs):
        record = frozen.get(objective)
        if record is None:
            return ResearchResult(objective=objective, sources=[], key_findings=[], is_mock=True)
        return ResearchResult(
            objective=objective,
            sources=[
                SearchSource(
                    title=s["title"], url=s["url"],
                    publish_date=s.get("publish_date"), excerpts=s.get("excerpts") or [],
                )
                for s in record["sources"]
            ],
            key_findings=[],
            confidence=ResearchConfidence(record.get("confidence", "HIGH")),
            is_mock=record.get("is_mock", False),
        )

    async def run():
        original = agent_mod.search_parallel
        agent_mod.search_parallel = replay
        try:
            scenario = get_scenario_by_id(sample_id)
            breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
            orchestrator = GreenlightOrchestrator()
            orchestrator.runner = _SilentRunner()
            async for _ in orchestrator.run_analysis_async(
                scenario.script_text, project_title=scenario.title, breakdown=breakdown
            ):
                pass
            return orchestrator.latest_brief
        finally:
            agent_mod.search_parallel = original

    return json.loads(asyncio.run(run()).model_dump_json())


def _build_explanation(brief):
    """Executes the real explain.js against a brief and returns the view model."""
    script = (
        "import { buildExplanation } from %s;\n"
        "import { readFileSync } from 'node:fs';\n"
        "const brief = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
        "process.stdout.write(JSON.stringify(buildExplanation(brief)));\n"
        % json.dumps(EXPLAIN_JS.as_uri())
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        runner = tmp / "runner.mjs"
        payload = tmp / "brief.json"
        runner.write_text(script, encoding="utf-8")
        payload.write_text(json.dumps(brief), encoding="utf-8")
        result = subprocess.run(
            [NODE, str(runner), str(payload)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# ------------------------------------------------ explain.js: real execution


@requires_node
@pytest.mark.parametrize("sample_id", CURATED)
def test_displayed_calculation_reconstructs_the_published_score(sample_id, frozen):
    """The headline requirement: the panel's arithmetic must add up."""
    brief = _brief(sample_id, frozen)
    model = _build_explanation(brief)

    assert model is not None, "every brief must carry a displayable calculation"
    assert model["reconstructionHolds"] is True, sample_id
    assert model["reconstructed"] == model["finalScore"]
    assert model["finalScore"] == brief["scorecard"]["readiness_score"]

    # The running total shown against each step must chain correctly.
    running = model["startingScore"]
    for row in model["rows"]:
        assert row["before"] == running
        assert row["before"] - row["penalty"] >= row["after"]
        running = row["after"]


@requires_node
@pytest.mark.parametrize("sample_id", CURATED)
def test_every_dependency_is_shown_with_its_severity_and_impact(sample_id, frozen):
    brief = _brief(sample_id, frozen)
    model = _build_explanation(brief)

    shown = {row["element"] for row in model["rows"]}
    assessed = {d["element"] for d in brief["assessed_dependencies"]}
    assert shown == assessed, "a judge must see every dependency that moved the score"

    for row in model["rows"]:
        assert row["severity"] in {"CRITICAL", "HIGH", "MODERATE", "LOW"}
        assert row["sharePercent"] >= 0
        assert row["rationale"]


@requires_node
def test_inherent_baseline_is_not_presented_as_evidence(frozen):
    """Brooklyn's Work at Height is HIGH with no supporting source.

    Presenting it beside an FAA citation as though both were evidence-backed
    would misrepresent what the system actually established.
    """
    brief = _brief("brooklyn-drone-chase", frozen)
    model = _build_explanation(brief)
    rows = {row["element"]: row for row in model["rows"]}

    height = rows["Work at Height / Fall Exposure"]
    assert height["basis"] == "INHERENT"
    assert height["evidenceBacked"] is False
    assert height["citation"] is None
    assert "baseline" in height["basisNote"].lower()

    drone = rows["Low-altitude Drone Flight"]
    assert drone["basis"] == "REGULATORY"
    assert drone["evidenceBacked"] is True
    assert drone["citation"] is not None
    assert drone["citation"]["source_url"]


@requires_node
def test_basis_is_keyed_on_provenance_not_severity(frozen):
    """Two HIGH dependencies can have entirely different evidentiary standing."""
    brief = _brief("brooklyn-drone-chase", frozen)
    model = _build_explanation(brief)
    highs = [r for r in model["rows"] if r["severity"] == "HIGH"]

    assert len(highs) >= 2
    assert {r["evidenceBacked"] for r in highs} == {True, False}, (
        "the panel must distinguish evidence-backed HIGH from baseline HIGH"
    )


@requires_node
def test_hard_stops_distinguish_ceiling_from_verdict_constraint(frozen):
    """A ceiling changes the number; a constraint changes only the call.

    Asserted as a property across the curated set rather than pinned to one
    scenario, since which stops fire depends on the evidence of the day.
    """
    capping = []
    constraints = []

    for sample_id in CURATED:
        model = _build_explanation(_brief(sample_id, frozen))
        for stop in model["hardStops"]:
            assert stop["ruleId"]
            assert stop["reason"]
            if stop["scoreCap"] is None:
                assert stop["affectsScore"] is False, (sample_id, stop["ruleId"])
                constraints.append(stop["ruleId"])
            else:
                assert stop["affectsScore"] is True, (sample_id, stop["ruleId"])
                capping.append(stop["ruleId"])

    assert capping, "no ceiling stop fired anywhere in the curated set"
    assert constraints, "no verdict-only constraint fired anywhere in the curated set"


@requires_node
def test_unadopted_mitigation_is_reported_as_not_reducing_risk(frozen):
    brief = _brief("brooklyn-drone-chase", frozen)
    model = _build_explanation(brief)
    offered = [r for r in model["rows"] if r["mitigationOffered"]]
    for row in offered:
        assert row["mitigationAdopted"] is False
        assert row["factors"] == [] or all("adopted mitigation" not in f for f in row["factors"])


@requires_node
def test_jurisdiction_is_surfaced(frozen):
    for sample_id, expected in [
        ("brooklyn-drone-chase", "New York"),
        ("svalbard-arctic", "Svalbard"),
        ("stage-interior-dialogue", "Los Angeles"),
    ]:
        model = _build_explanation(_brief(sample_id, frozen))
        assert expected in (model["jurisdiction"] or ""), (sample_id, model["jurisdiction"])


@requires_node
def test_controlled_production_shows_a_short_clean_calculation(frozen):
    """A GREEN result must still explain itself."""
    model = _build_explanation(_brief("stage-interior-dialogue", frozen))
    assert model["finalScore"] >= 85
    assert model["rows"], "even a clean production shows what was assessed"
    assert model["hardStops"] == []
    assert model["reconstructionHolds"] is True


# --------------------------------------------------------- wiring contract


def test_explain_module_exposes_the_required_surface():
    source = EXPLAIN_JS.read_text(encoding="utf-8")
    for symbol in ("buildExplanation", "reconstructScore", "classifyBasis", "primaryCitation"):
        assert f"export function {symbol}" in source, symbol
    # Basis must be decided by provenance, never by the severity value alone.
    assert "signal_provenance" in source


def test_decision_card_hosts_the_explanation_panel():
    markup = INDEX.read_text(encoding="utf-8")
    for token in (
        'id="toggleExplain"', 'id="explainPanel"', 'id="explainSteps"',
        'id="explainStops"', 'id="explainCheck"', 'id="explainJurisdiction"',
    ):
        assert token in markup, token
    # Collapsed by default: the decision card stays a decision card.
    assert 'id="explainPanel" class="explain-panel hidden"' in markup
    assert 'aria-expanded="false"' in markup


def test_app_renders_and_resets_the_explanation():
    source = APP_JS.read_text(encoding="utf-8")
    assert "buildExplanation" in source
    assert "renderExplanation(brief)" in source
    assert "clearExplanation()" in source
    assert "toggleExplain?.addEventListener" in source


def test_existing_behaviour_is_untouched():
    """Explainability is additive: cache, reset and analyze rules stand."""
    source = APP_JS.read_text(encoding="utf-8")
    assert source.count("resultCache.clear()") == 1
    assert "resultCache.delete(" not in source
    assert "renderCached(" in source
    assert "'Analyzed'" not in source


# ------------------------------------------------------------- D1 - D5


@requires_node
@pytest.mark.parametrize("sample_id", CURATED)
def test_decision_basis_distinguishes_hard_stop_from_cumulative(sample_id, frozen):
    """D2: a RED reached by accumulation must not borrow blocker language."""
    brief = _brief(sample_id, frozen)
    model = _build_explanation(brief)

    criticals = [r for r in model["rows"] if r["severity"] == "CRITICAL"]
    ceilings = [s for s in model["hardStops"] if s["affectsScore"]]
    expected = "HARD_STOP" if (criticals or ceilings) else "CUMULATIVE"

    assert model["decisionBasis"] == expected, sample_id
    assert model["decisionBasisLabel"]

    headline = brief["scorecard"]["verdict_headline"]
    if model["decisionBasis"] == "CUMULATIVE":
        assert "PRODUCTION BLOCKED" not in headline, headline
        assert brief["scorecard"]["red_count"] == 0, "cumulative RED must not claim RED dependencies"
    else:
        assert "BLOCKED" in headline, headline


@requires_node
def test_cumulative_headline_never_contradicts_the_counts_row(frozen):
    """The counts row and the headline must tell the same story."""
    for sample_id in CURATED:
        brief = _brief(sample_id, frozen)
        card = brief["scorecard"]
        if "PRODUCTION BLOCKED" in card["verdict_headline"]:
            has_ceiling = any(
                s.get("score_cap") is not None
                for s in card["score_breakdown"]["hard_stops"]
            )
            assert card["red_count"] > 0 or has_ceiling, (
                f"{sample_id}: headline says BLOCKED with {card['red_count']} Red and no ceiling"
            )


@requires_node
@pytest.mark.parametrize("sample_id", CURATED)
def test_every_dependency_carries_its_screenplay_phrases(sample_id, frozen):
    """D5: the first link of the trace is present in the model."""
    brief = _brief(sample_id, frozen)
    model = _build_explanation(brief)
    script = get_scenario_by_id(sample_id).script_text.lower()

    for row in model["rows"]:
        assert isinstance(row["triggers"], list)
        assert row["scenes"], row["element"]
        # Phrases are the backend's, taken verbatim from the page.
        for phrase in row["triggers"]:
            assert phrase.lower() in script, (row["element"], phrase)


@requires_node
def test_brooklyn_drone_shows_its_actual_screenplay_phrases(frozen):
    model = _build_explanation(_brief("brooklyn-drone-chase", frozen))
    drone = next(r for r in model["rows"] if r["element"] == "Low-altitude Drone Flight")
    assert drone["triggers"], "the drone dependency must cite the words that produced it"
    assert {t.lower() for t in drone["triggers"]} & {"drone", "fpv"}


@requires_node
@pytest.mark.parametrize("sample_id", CURATED)
def test_mitigation_is_hazard_specific(sample_id, frozen):
    """D3: distinct hazards must not receive identical advice."""
    brief = _brief(sample_id, frozen)
    actions = [d["recommended_action"] for d in brief["assessed_dependencies"]]
    assert len(set(actions)) == len(actions), (
        f"{sample_id}: identical mitigation across distinct hazards"
    )


def test_soundstage_does_not_claim_public_location_permitting():
    """D4: an interior permitted-stage scene is not public-location filming."""
    from server.services.script_parser import ScriptParser as SP

    scenario = get_scenario_by_id("stage-interior-dialogue")
    breakdown = SP.parse_text(scenario.script_text, project_title=scenario.title)
    dep = breakdown.scenes[0].dependencies[0]

    assert "public location" not in dep.risk_description.lower()
    assert "standing permit" in dep.risk_description.lower()
    assert dep.mitigation_template
    assert "public" not in dep.mitigation_template.lower()

    # An exterior street scene must keep the public-location wording.
    street = SP.parse_text(
        "EXT. QUIET LANE - DAY\n\nTwo neighbours talk over a fence.",
        project_title="Street",
    )
    assert "public location" in street.scenes[0].dependencies[0].risk_description.lower()


def test_frontend_shows_every_dependency_and_source():
    """D1: no silent truncation in Top Risks, Decision Chain or Evidence."""
    source = APP_JS.read_text(encoding="utf-8")
    assert "deps.slice(0, 4)" not in source
    assert "sources.slice(0, 5)" not in source
    # The dependency-to-source relationship is stated rather than implied.
    assert "source(s) cited across" in source


def test_explanation_renders_trigger_phrases_and_decision_basis():
    source = APP_JS.read_text(encoding="utf-8")
    assert "explain-from-page" in source
    assert "From the page:" in source
    assert "explain-decision-basis" in source
    assert "decisionBasisLabel" in source
