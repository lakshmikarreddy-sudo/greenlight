"""Contract tests for C1-C4: extraction depth, context, evidence binding, audit.

These lock the failure modes the architecture review found:

  C1  an Arctic glacier scene yielding one dependency and missing the cold,
      the crevasse field, the wildlife and the remoteness
  C2  dependencies floating free of the scene and jurisdiction that produced them
  C3  a Norwegian shoot assessed against a Texas prop-weapons page, and blocker
      claims sourced from commercial blogs
  C4  a published score that cannot be reproduced from its own explanation
"""

import pytest

from server.models.brief import AssessedDependency, ProductionStatus
from server.models.research import ResearchResult, SearchSource
from server.models.scoring import EvidenceConfidence, Severity
from server.services.evidence_binding import (
    MATCH_EXACT,
    MATCH_NONE,
    TIER_COMMERCIAL,
    TIER_STATUTORY,
    authority_tier,
    bind_sources,
    confidence_for,
    extract_lead_time,
)
from server.services.hazard_rules import detect_context, detect_hazards
from server.services.jurisdiction import resolve_jurisdiction
from server.services.script_parser import ScriptParser
from server.services.sample_library import get_scenario_by_id
from server.services.scoring import score_production


# ------------------------------------------------------------------ C1


def test_arctic_scene_surfaces_more_than_a_rifle():
    """The Svalbard failure: cold, ice, remoteness and wildlife were invisible."""
    scenario = get_scenario_by_id("svalbard-arctic")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    classes = {d.hazard_class for d in breakdown.scenes[0].dependencies}

    for required in ("EXTREME_COLD", "ICE_AND_CREVASSE", "REMOTE_OPERATIONS", "DANGEROUS_WILDLIFE"):
        assert required in classes, f"{required} missing from {sorted(classes)}"


@pytest.mark.parametrize(
    "sample_id,expected",
    [
        ("brooklyn-drone-chase", {"AVIATION_UAS", "TRAFFIC_AND_VEHICLES", "WORKING_AT_HEIGHT"}),
        ("savannah-pyro", {"PYROTECHNICS", "FIREARMS", "HERITAGE_PROPERTY"}),
    ],
)
def test_scenes_surface_their_defining_hazards(sample_id, expected):
    scenario = get_scenario_by_id(sample_id)
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    classes = {d.hazard_class for d in breakdown.scenes[0].dependencies}
    assert expected <= classes, f"{sorted(expected - classes)} missing"


def test_every_dependency_cites_the_words_that_produced_it():
    """Extraction must be auditable against the page."""
    scenario = get_scenario_by_id("savannah-pyro")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    text = scenario.script_text.lower()

    for dep in breakdown.scenes[0].dependencies:
        assert dep.trigger_phrases, dep.element
        for phrase in dep.trigger_phrases:
            assert phrase.lower() in text, (dep.element, phrase)


def test_extraction_does_not_fire_on_incidental_words():
    """'begun', 'cowboy' and 'in charge' are not production hazards."""
    prose = "He had begun the climb. A cowboy waited. Fifteen minutes later she was in charge."
    fired = {rule.hazard_class for rule, _ in detect_hazards(prose)}
    assert "FIREARMS" not in fired
    assert "MINORS" not in fired
    assert "PYROTECHNICS" not in fired


# ------------------------------------------------------------------ C2


def test_scene_context_is_captured():
    scenario = get_scenario_by_id("savannah-pyro")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    flags = set(breakdown.scenes[0].context_flags)
    assert "night_work" in flags
    assert "public_access" in flags


def test_dependencies_carry_their_scene_numbers():
    scenario = get_scenario_by_id("brooklyn-drone-chase")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    valid = {s.scene_number for s in breakdown.scenes}
    for scene in breakdown.scenes:
        for dep in scene.dependencies:
            assert dep.scene_numbers
            assert set(dep.scene_numbers) <= valid


@pytest.mark.parametrize(
    "location,expected_country",
    [
        ("SVALBARD GLACIER OUTLET", "Norway"),
        ("BROOKLYN BRIDGE", "United States"),
        ("MONTEREY SQUARE (SAVANNAH)", "United States"),
    ],
)
def test_jurisdiction_resolves_from_the_slugline(location, expected_country):
    assert resolve_jurisdiction(location).country == expected_country


def test_unknown_location_is_not_guessed():
    juris = resolve_jurisdiction("EXT. AN UNNAMED PLACE")
    assert juris.resolved is False
    assert juris.country is None


# ------------------------------------------------------------------ C3


@pytest.mark.parametrize(
    "url,tier",
    [
        ("https://www.nyc.gov/site/mome/permits/permits.page", TIER_STATUTORY),
        ("https://www.faa.gov/uas", TIER_STATUTORY),  # a .gov regulator is statutory
        ("https://www.thedroneu.com/blog/usa-drone-laws", TIER_COMMERCIAL),
    ],
)
def test_authority_tier_classification(url, tier):
    assert authority_tier(url) == tier


def _result(*sources):
    return ResearchResult(objective="o", sources=list(sources), key_findings=[])


def test_out_of_jurisdiction_source_does_not_bind():
    """The exact defect: a Texas page answering for a Norwegian shoot."""
    texas = SearchSource(
        title="Prop Weapons and Firearms - Office of the Texas Governor",
        url="https://gov.texas.gov/film/page/prop-weapons",
        excerpts=["Texas productions using prop weapons must notify local law enforcement."],
    )
    svalbard = resolve_jurisdiction("SVALBARD GLACIER OUTLET")
    bound, match = bind_sources(_result(texas), svalbard, "Firearms / Weapons", "FIREARMS")

    assert bound == [], "a Texas page must not answer for a Norwegian shoot"
    assert match == MATCH_NONE


def test_in_jurisdiction_authority_binds():
    source = SearchSource(
        title="Governor of Svalbard - firearms and polar bear protection",
        url="https://www.sysselmesteren.no/en/firearms",
        excerpts=["Anyone travelling outside settlements in Svalbard must carry firearms for polar bear protection."],
    )
    svalbard = resolve_jurisdiction("SVALBARD GLACIER OUTLET")
    bound, match = bind_sources(_result(source), svalbard, "Firearms / Weapons", "FIREARMS")

    assert len(bound) == 1
    assert match == MATCH_EXACT


def test_right_place_wrong_subject_does_not_bind():
    source = SearchSource(
        title="New York City parking regulations",
        url="https://www.nyc.gov/parking",
        excerpts=["Alternate side parking rules for New York City residents."],
    )
    nyc = resolve_jurisdiction("BROOKLYN BRIDGE")
    bound, _ = bind_sources(_result(source), nyc, "Pyrotechnic / Practical Explosion", "PYROTECHNICS")
    assert bound == []


def test_confidence_reflects_authority_not_just_count():
    statutory = SearchSource(
        title="NYC drone filming rules",
        url="https://www.nyc.gov/drones",
        excerpts=["Drone filming in New York City requires NYPD approval."],
    )
    blog = SearchSource(
        title="Best drone spots",
        url="https://www.dronefanblog.com/nyc",
        excerpts=["Drone flying in New York City is fun."],
    )
    nyc = resolve_jurisdiction("BROOKLYN BRIDGE")

    strong, m1 = bind_sources(_result(statutory), nyc, "Low-altitude Drone Flight", "AVIATION_UAS")
    weak, m2 = bind_sources(_result(blog), nyc, "Low-altitude Drone Flight", "AVIATION_UAS")

    assert confidence_for(strong, m1) == "HIGH"
    assert confidence_for(weak, m2) != "HIGH"


def test_lead_time_requires_application_context():
    """A number of days inside a safety bulletin is not a statutory lead time."""
    bulletin = SearchSource(
        title="Safety Bulletin #16 Pyrotechnics",
        url="https://www.csatf.org/16PYROTECHNIC.pdf",
        excerpts=["Pyrotechnic charges should be stored no longer than 15 days on set."],
    )
    permit = SearchSource(
        title="Savannah film permit",
        url="https://www.savannahga.gov/film",
        excerpts=["Pyrotechnic permit applications must be submitted at least 45 days in advance."],
    )
    savannah = resolve_jurisdiction("MONTEREY SQUARE (SAVANNAH)")

    bound_b, _ = bind_sources(_result(bulletin), savannah, "Pyrotechnic / Practical Explosion", "PYROTECHNICS")
    bound_p, _ = bind_sources(_result(permit), savannah, "Pyrotechnic / Practical Explosion", "PYROTECHNICS")

    assert extract_lead_time(bound_b) is None
    found = extract_lead_time(bound_p)
    assert found is not None and found[1] == 45


# ------------------------------------------------------------------ C4


def _dep(**kw):
    base = dict(
        element="X",
        category="SAFETY_AND_STUNTS",
        status=ProductionStatus.YELLOW,
        risk_description="d",
        recommended_action="a",
        confidence=EvidenceConfidence.HIGH,
        jurisdiction_match="EXACT",
        bound_source_count=2,
        supervision_confirmed=True,
    )
    base.update(kw)
    return AssessedDependency(**base)


def test_explanation_reproduces_the_score_step_by_step():
    """Every line is arithmetic; the last line follows from the ones above."""
    deps = [
        _dep(element="A", regulatory_exposure=True),
        _dep(element="B", safety_exposure=True),
        _dep(element="C", permitting_exposure=True, lead_time_days=45),
    ]
    breakdown = score_production(deps)

    assert breakdown.reconstruct() == breakdown.final_score

    for c in breakdown.contributions:
        assert c.readiness_before - c.final_penalty >= c.readiness_after
        assert c.final_penalty == int(round(c.readiness_before * c.risk_fraction))

    lines = breakdown.explain()
    assert lines[0] == "Starting readiness: 100."
    assert lines[-1] == f"Final readiness: {breakdown.final_score}."
    for c in breakdown.contributions:
        assert any(c.element in line and f"-{c.final_penalty}" in line for line in lines)


def test_explanation_shows_risk_share_not_only_points():
    """Ordering must not be mistaken for relative importance."""
    breakdown = score_production([
        _dep(element="A", regulatory_exposure=True),
        _dep(element="B", safety_exposure=True),
    ])
    lines = breakdown.explain()
    assert any("% of remaining readiness" in line for line in lines)


def test_hard_stop_ceiling_is_visible_in_the_explanation():
    breakdown = score_production([_dep(element="A", regulatory_exposure=True)])
    lines = breakdown.explain()
    assert any("ceiling" in line.lower() for line in lines)
    assert breakdown.reconstruct() == breakdown.final_score


def test_every_signal_that_fired_has_provenance():
    """A displayed verdict must name the source that produced it."""
    from server.agent.greenlight_agent import extract_bound_signals
    from server.models.screenplay import DependencyCategory, ProductionDependency

    dep = ProductionDependency(
        element="Low-altitude Drone Flight",
        category=DependencyCategory.PERMITS_AND_LEGAL,
        risk_description="d",
        hazard_class="AVIATION_UAS",
        blocker_terms=["waiver", "airspace", "drone"],
    )
    result = _result(SearchSource(
        title="FAA drone waivers",
        url="https://www.faa.gov/uas/waivers",
        excerpts=["Drone flight over moving vehicles in New York is prohibited without a waiver."],
    ))
    signals = extract_bound_signals(dep, result, resolve_jurisdiction("BROOKLYN BRIDGE"))

    assert signals["regulatory_exposure"] is True
    names = {p.signal for p in signals["signal_provenance"]}
    assert "regulatory_exposure" in names
    for p in signals["signal_provenance"]:
        assert p.source_url
        assert p.matched_text


# ------------------------------------------------- hardening pass additions


def test_aviation_queries_reflect_the_scene_context():
    """A night flight over traffic must ask about night operations.

    The drone was previously researched with two generic queries, so the
    evidence never spoke to what the scene actually depicts.
    """
    from server.agent.greenlight_agent import build_queries

    scenario = get_scenario_by_id("brooklyn-drone-chase")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    scene = breakdown.scenes[0]
    juris = resolve_jurisdiction(scene.slugline.location)

    drone = next(d for d in scene.dependencies if d.hazard_class == "AVIATION_UAS")
    queries = " | ".join(build_queries(drone, juris)).lower()

    assert "part 107" in queries
    assert "over people" in queries or "moving vehicles" in queries
    assert "night" in queries, "night scene must raise the night-operations rule"
    assert "new york" in queries, "queries must be jurisdiction-qualified"


def test_context_queries_are_not_raised_for_daytime_interiors():
    """Context templates fire on context, not on the hazard class alone."""
    from server.agent.greenlight_agent import build_queries

    scenario = get_scenario_by_id("stage-interior-dialogue")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    scene = breakdown.scenes[0]
    assert "night_work" not in scene.context_flags

    dep = scene.dependencies[0]
    assert dep.context_query_templates == []
    assert build_queries(dep, resolve_jurisdiction(scene.slugline.location))


def test_blocker_needs_a_stated_prohibition_not_a_menu_item():
    """"Part 107 Waiver" in a navigation list is not a prohibition."""
    from server.services.evidence_binding import find_blocker

    menu = SearchSource(
        title="FAA UAS",
        url="https://www.faa.gov/uas",
        excerpts=["Become a Drone Pilot | Operations Over People | Part 107 Waiver | UAS Facility Maps"],
    )
    nyc = resolve_jurisdiction("BROOKLYN BRIDGE")
    bound, _ = bind_sources(_result(menu), nyc, "Low-altitude Drone Flight", "AVIATION_UAS")
    assert find_blocker(bound, ["drone", "waiver", "part 107"]) is None


def test_blocker_needs_an_exemption_instrument_not_just_a_control():
    """"Prohibited without fall protection" is a control, not a gate."""
    from server.services.evidence_binding import find_blocker

    control = SearchSource(
        title="NY fall protection",
        url="https://www.dot.ny.gov/fall-protection",
        excerpts=[
            "Employees in New York are prohibited from working at height without "
            "approved fall protection equipment and a rescue plan."
        ],
    )
    gating = SearchSource(
        title="FAA operations over people",
        url="https://www.faa.gov/uas/operations_over_people",
        excerpts=[
            "Drone flight over moving vehicles in New York is prohibited unless the "
            "operator holds an approved Part 107 waiver or authorization."
        ],
    )
    nyc = resolve_jurisdiction("BROOKLYN BRIDGE")

    bound_c, _ = bind_sources(_result(control), nyc, "Work at Height / Fall Exposure", "WORKING_AT_HEIGHT")
    bound_g, _ = bind_sources(_result(gating), nyc, "Low-altitude Drone Flight", "AVIATION_UAS")

    assert find_blocker(bound_c, ["height", "fall protection", "rigging"]) is None
    assert find_blocker(bound_g, ["drone", "waiver", "moving vehicles"]) is not None


def test_controlled_scene_extracts_no_hazards():
    """The low-risk scenario must be low-risk because nothing is there."""
    scenario = get_scenario_by_id("stage-interior-dialogue")
    breakdown = ScriptParser.parse_text(scenario.script_text, project_title=scenario.title)
    classes = {d.hazard_class for d in breakdown.scenes[0].dependencies}
    assert classes == {"LOCATION_PERMIT"}, classes
    assert breakdown.scenes[0].context_flags == []
