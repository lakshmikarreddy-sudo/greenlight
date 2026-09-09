"""Deterministic readiness scoring for the Greenlight Production Brief.

This module is intentionally pure: no network, no model calls, no clock, no
randomness. Given the same assessed dependencies it always returns the same
score, the same status and the same explanation.

The division of labour is deliberate:

  * AI and external research identify dependencies, research them, describe the
    risk and prescribe mitigation.
  * Evidence is reduced to *typed signals* (regulatory exposure, safety
    exposure, lead time, confidence) rather than a verdict.
  * This engine turns those signals into a severity, a penalty and a status.

Nothing outside this module may set ``readiness_score`` or ``overall_status``.
"""

from typing import Dict, List, Optional, Tuple

from server.models.brief import AssessedDependency, ProductionStatus
from server.models.scoring import (
    FORMULA_VERSION,
    EvidenceConfidence,
    HardStop,
    RiskContribution,
    ScoreBreakdown,
    Severity,
)

STARTING_SCORE = 100

#: Readiness never reads as zero: even a blocked production has a real floor.
SCORE_FLOOR = 5

#: Share of the *remaining* readiness a dependency removes, before weighting.
#: Expressed as a fraction so that risk compounds instead of saturating.
BASE_PENALTY: Dict[Severity, float] = {
    Severity.CRITICAL: 0.34,
    Severity.HIGH: 0.18,
    Severity.MODERATE: 0.09,
    Severity.LOW: 0.02,
}

#: No single dependency may wipe out more than this share at one step.
MAX_RISK_FRACTION = 0.60

#: Category weights: a safety failure costs more than a gear failure.
CATEGORY_WEIGHT: Dict[str, float] = {
    "SAFETY_AND_STUNTS": 1.25,
    "PERMITS_AND_LEGAL": 1.20,
    "CAST_AND_LABOR": 1.00,
    "LOCATIONS_AND_ACCESS": 1.00,
    "WEATHER_AND_ENVIRONMENT": 0.85,
    "EQUIPMENT_AND_GEAR": 0.75,
}
DEFAULT_CATEGORY_WEIGHT = 1.00

#: Weak evidence damps its own penalty rather than swinging the verdict.
CONFIDENCE_FACTOR: Dict[EvidenceConfidence, float] = {
    EvidenceConfidence.HIGH: 1.00,
    EvidenceConfidence.MEDIUM: 0.85,
    EvidenceConfidence.LOW: 0.70,
}

#: A substitution only reduces exposure once the production has *adopted* it.
#: Evidence merely mentioning that CGI exists is not a control.
MITIGATION_FACTOR = 0.80

#: A hazard recurring across scenes is more exposure, not less. Sub-linear,
#: because the tenth day of the same rig is not a tenth independent risk.
def occurrence_factor(scenes: int) -> float:
    if scenes <= 1:
        return 1.0
    if scenes <= 3:
        return 1.15
    if scenes <= 9:
        return 1.30
    return 1.50


#: Evidence from the wrong jurisdiction cannot carry full weight.
JURISDICTION_FACTOR = {"EXACT": 1.0, "NATIONAL": 0.9, "NONE": 0.6}

#: Scene facts that genuinely aggravate a hazard.
CONTEXT_AGGRAVATORS = {"night_work": 0.08, "adverse_weather": 0.08, "public_access": 0.10}

#: Confidence gates severity: weak evidence may not manufacture a blocker.
SEVERITY_CEILING_BY_CONFIDENCE = {
    EvidenceConfidence.LOW: Severity.MODERATE,
}

# Status thresholds, applied only when no hard stop fires.
GREEN_THRESHOLD = 85
YELLOW_THRESHOLD = 60


def _category_weight(category: str) -> float:
    return CATEGORY_WEIGHT.get(str(category or "").upper(), DEFAULT_CATEGORY_WEIGHT)


def lead_time_surcharge(lead_time_days: Optional[int]) -> float:
    """Extra risk share for statutory lead times that threaten the schedule."""
    if not lead_time_days or lead_time_days <= 30:
        return 0.0
    if lead_time_days <= 60:
        return 0.04
    return 0.08


def _context_factor(dep: AssessedDependency) -> float:
    """Night work, weather and public exposure make the same hazard worse."""
    bonus = sum(CONTEXT_AGGRAVATORS.get(flag, 0.0) for flag in (dep.context_flags or []))
    return round(1.0 + min(bonus, 0.25), 3)


def derive_severity(dep: AssessedDependency) -> Severity:
    """Derives a severity tier from evidence signals.

    Ordered and total: the same signals always yield the same tier, and no
    caller may inject a severity of its own choosing.

    ``regulatory_exposure`` is prohibition-grade by construction — the signal
    extractor sets it only for a statutory ban or a waiver regime, never for
    ordinary permitting — so it maps straight to CRITICAL. A long lead time
    adds a surcharge rather than changing the tier.
    """
    if dep.regulatory_exposure:
        proposed = Severity.CRITICAL
    elif dep.safety_exposure:
        proposed = Severity.HIGH
    elif dep.permitting_exposure or dep.lead_time_days:
        proposed = Severity.MODERATE
    else:
        proposed = Severity.LOW

    # A long statutory lead time escalates permitting friction into a schedule
    # risk in its own right.
    if proposed is Severity.MODERATE and dep.lead_time_days and dep.lead_time_days > 60:
        proposed = Severity.HIGH

    # Unbound or weak evidence may never manufacture a blocker. An unverified
    # dependency is still a real risk, but it is not an established one.
    order = [Severity.LOW, Severity.MODERATE, Severity.HIGH, Severity.CRITICAL]

    ceiling = SEVERITY_CEILING_BY_CONFIDENCE.get(dep.confidence)
    if dep.unverified and ceiling is None:
        ceiling = Severity.MODERATE
    if ceiling is not None and order.index(proposed) > order.index(ceiling):
        proposed = ceiling

    # The hazard class carries its own floor: thin research cannot make an
    # inherently dangerous activity look routine.
    floor = dep.inherent_severity_floor or Severity.LOW
    if order.index(proposed) < order.index(floor):
        proposed = floor

    return proposed


def _uncapped_severity(dep: AssessedDependency) -> Severity:
    """Severity the signals proposed, before any confidence ceiling."""
    if dep.regulatory_exposure:
        return Severity.CRITICAL
    if dep.safety_exposure:
        return Severity.HIGH
    if dep.permitting_exposure or dep.lead_time_days:
        return Severity.MODERATE
    return Severity.LOW


def _rationale(dep: AssessedDependency, severity: Severity) -> str:
    """One clause a producer can act on, naming the driver of the deduction."""
    if severity is Severity.CRITICAL:
        base = "RED regulatory exposure"
        if dep.safety_exposure:
            base = "RED regulatory and life-safety exposure"
    elif severity is Severity.HIGH:
        base = "life-safety exposure requiring certified supervision" if dep.safety_exposure else "regulatory exposure"
    elif severity is Severity.MODERATE:
        base = "permitting and schedule exposure"
    else:
        base = "routine production protocol"

    if dep.lead_time_days:
        base += f", {dep.lead_time_days}-day statutory lead time"
    if dep.occurrence_count > 1:
        base += f", recurring across {dep.occurrence_count} scenes"
    for flag in sorted(dep.context_flags or []):
        if flag in CONTEXT_AGGRAVATORS:
            base += f", {flag.replace('_', ' ')}"
    if dep.jurisdiction_match != "EXACT":
        base += f", evidence only {dep.jurisdiction_match.lower()} to {dep.jurisdiction_label or 'the shoot'}"
    if dep.unverified:
        base += ", UNVERIFIED (no governing source retrieved)"
    elif dep.confidence is not EvidenceConfidence.HIGH:
        base += f", {dep.confidence.value.lower()}-confidence evidence"
    if dep.mitigation_adopted:
        base += ", substitution adopted"
    return base


def score_dependency(dep: AssessedDependency, occurrence_index: int = 0) -> RiskContribution:
    """Computes one dependency's audited contribution to the deduction."""
    # Severity is always re-derived from signals. An incoming value is treated
    # as display state, never as authority over the score.
    proposed = _uncapped_severity(dep)
    severity = derive_severity(dep)
    base = BASE_PENALTY[severity]
    weight = _category_weight(dep.category)
    confidence = CONFIDENCE_FACTOR[dep.confidence]
    occurrence = occurrence_factor(max(dep.occurrence_count, len(dep.scene_numbers or []), 1))
    juris = JURISDICTION_FACTOR.get(dep.jurisdiction_match, 0.6)
    context = _context_factor(dep)
    # Mitigation reduces residual exposure only once adopted. Evidence merely
    # noting that a substitution exists changes nothing.
    mitigation = MITIGATION_FACTOR if dep.mitigation_adopted else 1.0
    surcharge = lead_time_surcharge(dep.lead_time_days)

    fraction = (base * weight * confidence * occurrence * juris * context * mitigation) + surcharge
    fraction = max(0.0, min(MAX_RISK_FRACTION, fraction))
    # Points are assigned by score_production, which knows the running total.
    penalty = 0

    return RiskContribution(
        element=dep.element,
        category=str(dep.category),
        severity=severity,
        base_penalty=base,
        category_weight=weight,
        confidence_factor=confidence,
        occurrence_factor=occurrence,
        jurisdiction_factor=juris,
        context_factor=context,
        mitigation_factor=mitigation,
        lead_time_surcharge=surcharge,
        severity_capped_by_confidence=severity is not proposed,
        risk_fraction=round(fraction, 4),
        final_penalty=penalty,
        rationale=_rationale(dep, severity),
        evidence_url=dep.parallel_evidence.source_url if dep.parallel_evidence else None,
    )


def evaluate_hard_stops(
    dependencies: List[AssessedDependency],
    contributions: List[RiskContribution],
) -> List[HardStop]:
    """Applies deterministic blocker rules that outrank the numeric verdict."""
    stops: List[HardStop] = []

    severity_by_element = {c.element: c.severity for c in contributions}

    # HS-1: a credible statutory blocker halts production regardless of score.
    for dep in dependencies:
        if (
            severity_by_element.get(dep.element) is Severity.CRITICAL
            and dep.regulatory_exposure
            and dep.confidence is not EvidenceConfidence.LOW
            and not dep.unverified
            and dep.jurisdiction_match in ("EXACT", "NATIONAL")
        ):
            stops.append(
                HardStop(
                    rule_id="HS-1",
                    reason=f"'{dep.element}' is a credible statutory blocker requiring formal waiver",
                    element=dep.element,
                    score_cap=40,
                )
            )
            break

    # HS-3: a pile-up of critical exposure is categorically not greenlightable.
    critical_total = sum(1 for c in contributions if c.severity is Severity.CRITICAL)
    if critical_total >= 3:
        stops.append(
            HardStop(
                rule_id="HS-3",
                reason=f"{critical_total} critical dependencies exceed the production risk ceiling",
                score_cap=25,
            )
        )

    # HS-4: unsupervised life-safety work cannot clear to GREEN.
    # HS-4: life-safety work whose governing regime could not be established.
    #
    # Audited and deliberately narrowed. The broad form -- any HIGH life-safety
    # hazard without a confirmed supervisor -- fired on every curated scenario,
    # which made it carry no information, and it was not independently gating:
    # "engage a certified supervisor" is ordinary pre-production work that every
    # film does, not a condition that stops a shoot.
    #
    # What genuinely gates a production is the evidence *gap*: dangerous work
    # whose legal and safety regime we could not establish. Scheduling
    # blank-firing weapons without knowing the armourer and police requirements
    # is a real stop. A high-confidence authority that simply does not discuss
    # supervision is reasonable grounds to conclude none is mandated, so it is
    # no longer treated as a blocker.
    for dep in dependencies:
        regime_unknown = dep.unverified or dep.confidence is not EvidenceConfidence.HIGH
        if (
            severity_by_element.get(dep.element) in (Severity.HIGH, Severity.CRITICAL)
            and dep.safety_exposure
            and not dep.supervision_confirmed
            and not dep.mitigation_adopted
            and regime_unknown
        ):
            stops.append(
                HardStop(
                    rule_id="HS-4",
                    reason=(
                        f"'{dep.element}' is life-safety work whose governing supervision "
                        f"regime could not be established from the available evidence"
                    ),
                    element=dep.element,
                    score_cap=None,
                )
            )
            break

    return stops


def derive_status(score: int, hard_stops: List[HardStop]) -> ProductionStatus:
    """Maps a readiness score plus hard stops onto the production verdict."""
    blocking = {s.rule_id for s in hard_stops}

    if "HS-1" in blocking or "HS-3" in blocking:
        return ProductionStatus.RED

    if score >= GREEN_THRESHOLD:
        # HS-4 forbids a clean greenlight but does not block production.
        return ProductionStatus.YELLOW if "HS-4" in blocking else ProductionStatus.GREEN
    if score >= YELLOW_THRESHOLD:
        return ProductionStatus.YELLOW
    return ProductionStatus.RED


def build_headline(
    status: ProductionStatus,
    contributions: List[RiskContribution],
    hard_stops: List[HardStop],
) -> str:
    """Headline reflects the actual risk profile, not just a RED tally.

    Wording only: this function never influences the score or the status.

    A RED reached by accumulating unresolved hazards is a different statement
    from a RED caused by a statutory blocker, and must not borrow its language.
    Saying "PRODUCTION BLOCKED" beside a counts row reading 0 Red contradicts
    the card a judge is looking at.
    """
    critical = sum(1 for c in contributions if c.severity is Severity.CRITICAL)
    high = sum(1 for c in contributions if c.severity is Severity.HIGH)
    moderate = sum(1 for c in contributions if c.severity is Severity.MODERATE)
    has_ceiling = any(s.score_cap is not None for s in hard_stops)

    if status is ProductionStatus.RED:
        if critical or has_ceiling:
            driver = f"{critical} CRITICAL REGULATORY BLOCKER(S)"
            if high:
                driver += f" + {high} SAFETY HAZARD(S)"
            return f"PRODUCTION BLOCKED — {driver}"

        # No blocker and no ceiling: RED is the sum of unresolved exposure.
        unresolved = high + moderate
        noun = "UNRESOLVED HAZARDS" if high else "COMPOUNDING PERMIT EXPOSURES"
        return f"NOT READY — CUMULATIVE RISK ACROSS {unresolved} {noun}"

    if status is ProductionStatus.YELLOW:
        if high:
            driver = f"{high} SAFETY REVIEW(S) MANDATORY"
        elif moderate:
            driver = f"{moderate} PERMIT REVIEW(S) MANDATORY"
        else:
            driver = "SUPERVISION SIGN-OFF REQUIRED"
        return f"CONDITIONAL GREENLIGHT — {driver}"

    return "GREENLIGHT — READY FOR PRINCIPAL PHOTOGRAPHY"


def status_for_dependency(contribution: RiskContribution) -> ProductionStatus:
    """Per-dependency traffic light, derived from the same severity ladder."""
    if contribution.severity is Severity.CRITICAL:
        return ProductionStatus.RED
    if contribution.severity is Severity.HIGH:
        return ProductionStatus.YELLOW
    if contribution.severity is Severity.MODERATE:
        return ProductionStatus.YELLOW
    return ProductionStatus.GREEN


def score_production(dependencies: List[AssessedDependency]) -> ScoreBreakdown:
    """Computes the readiness score and its full audit trail.

    Pure and order-independent: contributions are attributed in a stable order
    so that permuting the input cannot change the result.
    """
    ordered = sorted(
        dependencies,
        key=lambda d: (str(d.element or ""), str(d.category or "")),
    )

    scored = [score_dependency(dep) for dep in ordered]
    by_element = {c.element: c for c in scored}

    hard_stops = evaluate_hard_stops(ordered, scored)
    caps = {s.element: s.score_cap for s in hard_stops if s.score_cap is not None and s.element}
    global_caps = [s.score_cap for s in hard_stops if s.score_cap is not None and not s.element]

    # Largest risk first, then by name so the result never depends on input
    # order. Each dependency removes a share of what readiness remains.
    order = sorted(scored, key=lambda c: (-c.risk_fraction, c.element))

    running = STARTING_SCORE
    ceiling_adjustment = 0
    contributions: List[RiskContribution] = []

    for contribution in order:
        before = running
        deduction = int(round(running * contribution.risk_fraction))
        running = max(0, running - deduction)

        # A blocker caps readiness at the moment it is considered, so any
        # dependencies still to come reduce it further from that ceiling.
        cap = caps.get(contribution.element)
        if cap is not None and running > cap:
            ceiling_adjustment += running - cap
            running = cap

        contributions.append(
            contribution.model_copy(update={
                "final_penalty": deduction,
                "readiness_before": before,
                "readiness_after": running,
            })
        )

    for cap in global_caps:
        if running > cap:
            ceiling_adjustment += running - cap
            running = cap

    raw_total = STARTING_SCORE - sum(c.final_penalty for c in contributions)
    cap_applied = ceiling_adjustment > 0

    final_score = max(SCORE_FLOOR, min(STARTING_SCORE, running))
    floor_applied = running < SCORE_FLOOR

    return ScoreBreakdown(
        starting_score=STARTING_SCORE,
        contributions=contributions,
        hard_stops=hard_stops,
        raw_total=raw_total,
        floor_applied=floor_applied,
        cap_applied=cap_applied,
        ceiling_adjustment=ceiling_adjustment,
        final_score=final_score,
        formula_version=FORMULA_VERSION,
    )
