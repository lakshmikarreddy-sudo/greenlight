"""Deterministic tests for the readiness scoring engine.

These tests never touch the network, a model, or the clock. The scoring engine
is a pure function, so every expectation here is an exact integer.

They exist to lock down three defects the previous count-based scorer had:

  1. two different risk profiles collapsing to the same score because they
     happened to share a RED count,
  2. a dependency flipping RED/YELLOW between runs because a search result's
     wording changed,
  3. a published score that could not be explained to a judge.
"""

import pytest

from server.models.brief import AssessedDependency, ProductionStatus
from server.models.scoring import EvidenceConfidence, Severity
from server.services import scoring
from server.services.scoring import (
    GREEN_THRESHOLD,
    SCORE_FLOOR,
    STARTING_SCORE,
    YELLOW_THRESHOLD,
    derive_severity,
    derive_status,
    lead_time_surcharge,
    score_production,
)


def dep(
    element="Element",
    category="LOCATIONS_AND_ACCESS",
    *,
    regulatory=False,
    permitting=False,
    safety=False,
    lead_time=None,
    mitigation_adopted=False,
    mitigation_option=False,
    confidence=EvidenceConfidence.HIGH,
    jurisdiction_match="EXACT",
    scenes=1,
    context=(),
    unverified=False,
    supervision_confirmed=True,
    floor=Severity.LOW,
) -> AssessedDependency:
    """Builds an assessed dependency from signals alone."""
    return AssessedDependency(
        element=element,
        category=category,
        status=ProductionStatus.YELLOW,
        risk_description="fixture",
        recommended_action="fixture",
        regulatory_exposure=regulatory,
        permitting_exposure=permitting,
        safety_exposure=safety,
        lead_time_days=lead_time,
        mitigation_option_exists=mitigation_option,
        mitigation_adopted=mitigation_adopted,
        confidence=confidence,
        jurisdiction_match=jurisdiction_match,
        bound_source_count=0 if unverified else 2,
        unverified=unverified,
        supervision_confirmed=supervision_confirmed,
        inherent_severity_floor=floor,
        occurrence_count=scenes,
        scene_numbers=list(range(1, scenes + 1)),
        context_flags=list(context),
    )


# --------------------------------------------------------------- severity


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"regulatory": True}, Severity.CRITICAL),
        ({"regulatory": True, "safety": True}, Severity.CRITICAL),
        ({"safety": True}, Severity.HIGH),
        ({"lead_time": 30}, Severity.MODERATE),
        ({"permitting": True}, Severity.MODERATE),
        ({"permitting": True, "safety": True}, Severity.HIGH),
        ({"permitting": True, "regulatory": True}, Severity.CRITICAL),
        ({}, Severity.LOW),
    ],
)
def test_severity_is_derived_from_signals(kwargs, expected):
    assert derive_severity(dep(**kwargs)) is expected


def test_incoming_severity_is_never_trusted():
    """A caller cannot dictate severity; only signals decide it."""
    d = dep()  # no signals at all -> LOW
    d.severity = Severity.CRITICAL  # attacker/model tries to inflate
    breakdown = score_production([d])
    assert breakdown.contributions[0].severity is Severity.LOW


# ---------------------------------------------------------------- scoring


def test_empty_production_scores_full_readiness():
    breakdown = score_production([])
    assert breakdown.final_score == STARTING_SCORE
    assert derive_status(breakdown.final_score, breakdown.hard_stops) is ProductionStatus.GREEN


def test_known_profile_scores_exactly():
    """A blocker plus two permit dependencies, applied largest share first."""
    deps = [
        dep("Drone", "PERMITS_AND_LEGAL", regulatory=True, lead_time=90),
        dep("Traffic", "LOCATIONS_AND_ACCESS", lead_time=30),
        dep("Water", "WEATHER_AND_ENVIRONMENT", lead_time=30),
    ]
    breakdown = score_production(deps)
    by_element = {c.element: c for c in breakdown.contributions}

    # 0.34 * 1.20 = 0.408, plus a 0.08 long-lead surcharge -> 0.488
    assert by_element["Drone"].risk_fraction == 0.488
    # 0.09 * 1.00 -> 0.09 ; 0.09 * 0.85 -> 0.0765
    assert by_element["Traffic"].risk_fraction == 0.09
    assert by_element["Water"].risk_fraction == 0.0765

    # Deductions are proportional to the readiness remaining at each step.
    assert by_element["Drone"].readiness_before == 100
    assert by_element["Drone"].final_penalty == 49
    assert breakdown.final_score < 40  # HS-1 ceiling cannot be exceeded
    assert breakdown.reconstruct() == breakdown.final_score


def test_equal_red_counts_produce_different_scores():
    """The headline regression: same RED count must not mean the same score.

    Both profiles carry exactly one CRITICAL dependency. They must still be
    separated by category weight and by their other dependencies.
    """
    profile_a = [dep("Firearms", "SAFETY_AND_STUNTS", regulatory=True)]
    profile_b = [
        dep("Firearms", "SAFETY_AND_STUNTS", regulatory=True),
        dep("Pyro", "SAFETY_AND_STUNTS", safety=True),
    ]

    a = score_production(profile_a)
    b = score_production(profile_b)

    red_a = sum(1 for c in a.contributions if c.severity is Severity.CRITICAL)
    red_b = sum(1 for c in b.contributions if c.severity is Severity.CRITICAL)
    assert red_a == red_b == 1
    assert a.final_score != b.final_score


def test_category_weight_separates_identical_severities():
    """Same severity, different department: safety costs more than gear."""
    safety = score_production([dep("X", "SAFETY_AND_STUNTS", safety=True)])
    gear = score_production([dep("X", "EQUIPMENT_AND_GEAR", lead_time=30)])
    assert safety.final_score < gear.final_score


# ------------------------------------------------------------- properties


def test_score_is_order_independent():
    deps = [
        dep("A", "PERMITS_AND_LEGAL", regulatory=True),
        dep("B", "SAFETY_AND_STUNTS", safety=True),
        dep("C", "WEATHER_AND_ENVIRONMENT", lead_time=45),
    ]
    forward = score_production(deps).final_score
    backward = score_production(list(reversed(deps))).final_score
    assert forward == backward


def test_score_is_idempotent():
    deps = [dep("A", "PERMITS_AND_LEGAL", regulatory=True)]
    assert score_production(deps).final_score == score_production(deps).final_score


def test_adding_risk_never_raises_the_score():
    base = [dep("A", "SAFETY_AND_STUNTS", safety=True)]
    more = base + [dep("B", "PERMITS_AND_LEGAL", regulatory=True)]
    assert score_production(more).final_score <= score_production(base).final_score


def test_score_stays_within_bounds_under_heavy_load():
    deps = [
        dep(f"Blocker {i}", "SAFETY_AND_STUNTS", regulatory=True, safety=True, lead_time=180)
        for i in range(25)
    ]
    breakdown = score_production(deps)
    assert SCORE_FLOOR <= breakdown.final_score <= STARTING_SCORE


def test_deep_extraction_does_not_saturate_the_scale():
    """Five real hazards must not collapse to the floor.

    A flat additive model bottomed out as soon as extraction got good, which
    destroyed the score's ability to discriminate.
    """
    deps = [dep(f"H{i}", "SAFETY_AND_STUNTS", safety=True) for i in range(5)]
    breakdown = score_production(deps)
    assert breakdown.final_score > SCORE_FLOOR


def test_more_hazards_always_score_lower():
    three = score_production([dep(f"H{i}", "SAFETY_AND_STUNTS", safety=True) for i in range(3)])
    six = score_production([dep(f"H{i}", "SAFETY_AND_STUNTS", safety=True) for i in range(6)])
    assert six.final_score < three.final_score


def test_low_confidence_evidence_is_damped():
    """Weak evidence must not swing the verdict as hard as strong evidence."""
    strong = score_production([dep("A", "PERMITS_AND_LEGAL", regulatory=True, confidence=EvidenceConfidence.HIGH)])
    weak = score_production([dep("A", "PERMITS_AND_LEGAL", regulatory=True, confidence=EvidenceConfidence.LOW)])
    assert weak.raw_total > strong.raw_total


def test_recurring_hazard_costs_more_but_sub_linearly():
    """A hazard in ten scenes is more exposure than in one, but not ten times."""
    once = score_production([dep("Gun", "SAFETY_AND_STUNTS", safety=True, scenes=1)])
    many = score_production([dep("Gun", "SAFETY_AND_STUNTS", safety=True, scenes=10)])
    assert many.final_score < once.final_score
    single = STARTING_SCORE - once.final_score
    multi = STARTING_SCORE - many.final_score
    assert multi < single * 10


def test_mitigation_only_counts_once_adopted():
    """Evidence noting a substitution exists is not a control.

    An unadopted option must change nothing; only a confirmed adoption reduces
    residual exposure.
    """
    # A non-blocker dependency, so no hard-stop ceiling masks the difference.
    baseline = score_production([dep("A", "SAFETY_AND_STUNTS", safety=True)])
    option = score_production([dep("A", "SAFETY_AND_STUNTS", safety=True, mitigation_option=True)])
    adopted = score_production([dep("A", "SAFETY_AND_STUNTS", safety=True, mitigation_adopted=True)])

    assert option.final_score == baseline.final_score
    assert adopted.final_score > baseline.final_score


@pytest.mark.parametrize(
    "days,expected",
    [(None, 0.0), (10, 0.0), (30, 0.0), (31, 0.04), (60, 0.04), (61, 0.08), (365, 0.08)],
)
def test_lead_time_surcharge_tiers(days, expected):
    assert lead_time_surcharge(days) == expected


# ------------------------------------------------------------- hard stops


def test_hard_stop_caps_a_statutory_blocker():
    breakdown = score_production([
        dep("Drone", "PERMITS_AND_LEGAL", regulatory=True, confidence=EvidenceConfidence.HIGH)
    ])
    assert any(s.rule_id == "HS-1" for s in breakdown.hard_stops)
    assert breakdown.final_score <= 40
    assert derive_status(breakdown.final_score, breakdown.hard_stops) is ProductionStatus.RED


def test_low_confidence_does_not_trigger_a_hard_stop():
    """A blocker asserted only by weak evidence must not halt production."""
    breakdown = score_production([
        dep("Drone", "PERMITS_AND_LEGAL", regulatory=True, confidence=EvidenceConfidence.LOW)
    ])
    assert not any(s.rule_id == "HS-1" for s in breakdown.hard_stops)


def test_unverified_dependency_cannot_assert_a_blocker():
    """No bound evidence means no CRITICAL and no hard stop, but still a risk."""
    breakdown = score_production([
        dep("Drone", "PERMITS_AND_LEGAL", regulatory=True, unverified=True)
    ])
    assert breakdown.contributions[0].severity is not Severity.CRITICAL
    assert not any(s.rule_id == "HS-1" for s in breakdown.hard_stops)
    assert breakdown.final_score < STARTING_SCORE


def test_out_of_jurisdiction_evidence_is_damped():
    """Evidence that does not match the shoot's jurisdiction carries less weight."""
    exact = score_production([dep("A", "PERMITS_AND_LEGAL", regulatory=True, jurisdiction_match="EXACT")])
    none = score_production([dep("A", "PERMITS_AND_LEGAL", regulatory=True, jurisdiction_match="NONE")])
    assert none.final_score > exact.final_score


def test_inherent_floor_keeps_dangerous_hazards_off_the_bottom():
    """A -32C blizzard cannot read as routine because research was thin."""
    thin = dep("Extreme Cold", "WEATHER_AND_ENVIRONMENT", floor=Severity.HIGH)
    assert score_production([thin]).contributions[0].severity is Severity.HIGH


def test_scene_context_aggravates_the_same_hazard():
    """Night work and public access make an identical hazard worse."""
    plain = score_production([dep("A", "SAFETY_AND_STUNTS", safety=True)])
    aggravated = score_production([
        dep("A", "SAFETY_AND_STUNTS", safety=True, context=("night_work", "public_access"))
    ])
    assert aggravated.final_score < plain.final_score


def test_three_critical_dependencies_trip_the_ceiling():
    breakdown = score_production([
        dep("A", "PERMITS_AND_LEGAL", regulatory=True),
        dep("B", "SAFETY_AND_STUNTS", regulatory=True),
        dep("C", "LOCATIONS_AND_ACCESS", regulatory=True),
    ])
    assert any(s.rule_id == "HS-3" for s in breakdown.hard_stops)
    assert breakdown.final_score <= 25


def test_hs4_fires_only_when_the_regime_is_genuinely_unknown():
    """HS-4 was audited and narrowed; these lock the narrowed meaning.

    The broad form -- any HIGH life-safety hazard lacking a confirmed
    supervisor -- fired on every curated scenario and described ordinary
    pre-production work rather than a gating condition.
    """
    # Weak evidence and no supervision regime found: genuinely gating.
    # A life-safety hazard class carries a HIGH inherent floor, which is what
    # keeps it above the confidence ceiling -- exactly how firearms behaves.
    gap = dep(
        "Stunt", "SAFETY_AND_STUNTS", safety=True, floor=Severity.HIGH,
        supervision_confirmed=False, confidence=EvidenceConfidence.LOW,
    )
    assert any(s.rule_id == "HS-4" for s in score_production([gap]).hard_stops)

    # No bound evidence at all: also gating.
    unbound = dep("Stunt", "SAFETY_AND_STUNTS", safety=True, floor=Severity.HIGH,
                  supervision_confirmed=False, unverified=True)
    assert any(s.rule_id == "HS-4" for s in score_production([unbound]).hard_stops)

    # Strong evidence that simply does not mandate supervision: NOT gating.
    # A high-confidence authority silent on supervision is reasonable grounds
    # to conclude none is required.
    silent = dep(
        "Stunt", "SAFETY_AND_STUNTS", safety=True,
        supervision_confirmed=False, confidence=EvidenceConfidence.HIGH,
    )
    assert not any(s.rule_id == "HS-4" for s in score_production([silent]).hard_stops)

    # Supervision regime established: not gating.
    confirmed = dep("Stunt", "SAFETY_AND_STUNTS", safety=True, supervision_confirmed=True)
    assert not any(s.rule_id == "HS-4" for s in score_production([confirmed]).hard_stops)


def test_hs4_does_not_change_the_score():
    """HS-4 constrains the verdict; it must not silently move the number."""
    gap = dep("Stunt", "SAFETY_AND_STUNTS", safety=True, floor=Severity.HIGH,
              supervision_confirmed=False, confidence=EvidenceConfidence.LOW)
    breakdown = score_production([gap])
    stop = next(s for s in breakdown.hard_stops if s.rule_id == "HS-4")
    assert stop.score_cap is None
    assert breakdown.ceiling_adjustment == 0


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, ProductionStatus.GREEN),
        (GREEN_THRESHOLD, ProductionStatus.GREEN),
        (GREEN_THRESHOLD - 1, ProductionStatus.YELLOW),
        (YELLOW_THRESHOLD, ProductionStatus.YELLOW),
        (YELLOW_THRESHOLD - 1, ProductionStatus.RED),
        (5, ProductionStatus.RED),
    ],
)
def test_status_thresholds(score, expected):
    assert derive_status(score, []) is expected


# --------------------------------------------------------- explainability


def test_breakdown_arithmetic_is_reconstructible():
    """The published number must always follow from its own explanation."""
    deps = [
        dep("A", "PERMITS_AND_LEGAL", regulatory=True, lead_time=90),
        dep("B", "SAFETY_AND_STUNTS", safety=True),
        dep("C", "WEATHER_AND_ENVIRONMENT", lead_time=30),
    ]
    breakdown = score_production(deps)

    # Deliberately asserts invariants rather than re-implementing the formula,
    # so the test still has teeth if the weights change.
    deducted = sum(c.final_penalty for c in breakdown.contributions)
    assert breakdown.starting_score - deducted == breakdown.raw_total

    # A hard stop may only ever lower the published score.
    assert breakdown.final_score <= breakdown.raw_total
    assert breakdown.reconstruct() == breakdown.final_score

    # Every ceiling that fired is respected.
    for stop in breakdown.hard_stops:
        if stop.score_cap is not None:
            assert breakdown.final_score <= stop.score_cap

    assert SCORE_FLOOR <= breakdown.final_score <= STARTING_SCORE
    assert breakdown.explain()[-1] == f"Final readiness: {breakdown.final_score}."


def test_every_dependency_appears_in_the_explanation():
    deps = [dep("A"), dep("B", "SAFETY_AND_STUNTS", safety=True), dep("C", lead_time=45)]
    breakdown = score_production(deps)
    assert {c.element for c in breakdown.contributions} == {"A", "B", "C"}
    for contribution in breakdown.contributions:
        assert contribution.rationale


def test_explain_reads_as_a_judge_answer():
    breakdown = score_production([
        dep("Drone", "PERMITS_AND_LEGAL", regulatory=True, lead_time=90),
        dep("Water", "WEATHER_AND_ENVIRONMENT", lead_time=30),
    ])
    lines = breakdown.explain()
    assert lines[0] == "Starting readiness: 100."
    assert lines[-1] == f"Final readiness: {breakdown.final_score}."
    assert any("Drone" in line for line in lines)
    assert any("Water" in line for line in lines)


def test_contribution_factors_multiply_out_to_the_risk_share():
    """Each published factor must actually reproduce the risk share."""
    breakdown = score_production([
        dep("A", "SAFETY_AND_STUNTS", safety=True, lead_time=90, confidence=EvidenceConfidence.MEDIUM)
    ])
    c = breakdown.contributions[0]
    recomputed = (
        c.base_penalty * c.category_weight * c.confidence_factor
        * c.occurrence_factor * c.jurisdiction_factor * c.context_factor * c.mitigation_factor
    ) + c.lead_time_surcharge
    assert abs(c.risk_fraction - round(recomputed, 4)) < 1e-6
    # And the points removed must follow from the share and the running total.
    assert c.final_penalty == int(round(c.readiness_before * c.risk_fraction))


def test_every_score_is_reconstructable_from_its_breakdown():
    """The published number must follow from the audit trail alone."""
    for deps in (
        [dep("A", "PERMITS_AND_LEGAL", regulatory=True)],
        [dep("A", "PERMITS_AND_LEGAL", regulatory=True), dep("B", "SAFETY_AND_STUNTS", safety=True)],
        [dep(f"H{i}", "SAFETY_AND_STUNTS", safety=True) for i in range(6)],
    ):
        breakdown = score_production(deps)
        assert breakdown.reconstruct() == breakdown.final_score
        # Every step in explain() is arithmetic a reader can follow.
        lines = breakdown.explain()
        assert lines[0] == "Starting readiness: 100."
        assert lines[-1] == f"Final readiness: {breakdown.final_score}."


def test_formula_version_is_recorded():
    breakdown = score_production([dep("A")])
    assert breakdown.formula_version == scoring.FORMULA_VERSION
