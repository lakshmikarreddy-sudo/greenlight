// Readiness explainability: turns the backend's score_breakdown into the
// view model the Production Decision panel renders.
//
// Everything here is pure. It computes nothing about risk — the backend's
// deterministic engine already decided — it only makes that decision legible
// and, critically, arithmetically checkable on screen.

const SEVERITY_CLASS = {
  CRITICAL: 'status-red',
  HIGH: 'status-yellow',
  MODERATE: 'status-yellow',
  LOW: 'status-green',
};

// How a dependency's classification was reached. A judge must be able to tell
// an evidence-backed regulatory finding from a baseline the system applied
// because the hazard class is inherently dangerous — those are very different
// claims, and only the first is citable.
export const BASIS = {
  REGULATORY: 'REGULATORY',   // a governing source states a prohibition
  SUPERVISION: 'SUPERVISION', // evidence mandates certified supervision
  PERMITTING: 'PERMITTING',   // evidence mandates permits or lead time
  INHERENT: 'INHERENT',       // hazard-class baseline, no supporting signal
  UNVERIFIED: 'UNVERIFIED',   // no governing source could be bound at all
};

const BASIS_LABEL = {
  REGULATORY: 'Regulatory finding',
  SUPERVISION: 'Safety requirement',
  PERMITTING: 'Permitting requirement',
  INHERENT: 'Inherent hazard baseline',
  UNVERIFIED: 'Unverified',
};

const BASIS_NOTE = {
  REGULATORY: 'A governing authority states this activity is restricted pending an exemption.',
  SUPERVISION: 'Evidence requires certified supervision for this activity.',
  PERMITTING: 'Evidence requires permits, licensing or advance notice.',
  INHERENT: 'No governing source established this level. Applied from the hazard class baseline — treat as unconfirmed.',
  UNVERIFIED: 'No governing source could be bound to this dependency. Confirm directly with the authority.',
};

const SIGNAL_ORDER = ['regulatory_exposure', 'safety_exposure', 'permitting_exposure', 'lead_time_days'];

/**
 * Classifies why a dependency carries the severity it does.
 *
 * Deliberately keyed on signal provenance rather than the severity value:
 * Brooklyn's Work at Height is HIGH with zero provenance, and presenting that
 * as an evidence-backed finding would misrepresent what the system knows.
 */
export function classifyBasis(dep) {
  if (!dep) return BASIS.UNVERIFIED;
  if (dep.unverified) return BASIS.UNVERIFIED;

  const signals = new Set((dep.signal_provenance || []).map((p) => p.signal));
  if (signals.has('regulatory_exposure')) return BASIS.REGULATORY;
  if (signals.has('safety_exposure')) return BASIS.SUPERVISION;
  if (signals.has('permitting_exposure') || signals.has('lead_time_days')) return BASIS.PERMITTING;
  return BASIS.INHERENT;
}

export function basisLabel(basis) {
  return BASIS_LABEL[basis] || BASIS_LABEL.UNVERIFIED;
}

export function basisNote(basis) {
  return BASIS_NOTE[basis] || BASIS_NOTE.UNVERIFIED;
}

export function severityClass(severity) {
  return SEVERITY_CLASS[String(severity || '').toUpperCase()] || 'status-muted';
}

/**
 * Recomputes the published score from the breakdown alone.
 *
 * Mirrors ScoreBreakdown.reconstruct() on the backend. If this ever disagrees
 * with final_score the UI says so rather than quietly showing a number it
 * cannot justify.
 */
export function reconstructScore(breakdown) {
  if (!breakdown) return null;
  const start = Number(breakdown.starting_score ?? 100);
  const deducted = (breakdown.contributions || [])
    .reduce((sum, c) => sum + Number(c.final_penalty || 0), 0);
  let total = start - deducted - Number(breakdown.ceiling_adjustment || 0);
  if (breakdown.floor_applied) total = Math.max(total, Number(breakdown.final_score));
  return total;
}

export function reconstructionHolds(breakdown) {
  if (!breakdown) return false;
  return reconstructScore(breakdown) === Number(breakdown.final_score);
}

/** The strongest citation actually responsible for the classification. */
export function primaryCitation(dep) {
  const provenance = dep?.signal_provenance || [];
  if (!provenance.length) return null;
  for (const signal of SIGNAL_ORDER) {
    const hit = provenance.find((p) => p.signal === signal);
    if (hit) return hit;
  }
  return provenance[0];
}

/** Human-readable list of the multipliers that actually moved a penalty. */
export function activeFactors(contribution) {
  const factors = [];
  const add = (value, label) => {
    const v = Number(value);
    if (Number.isFinite(v) && Math.abs(v - 1) > 0.001) factors.push(`${label} x${v}`);
  };
  add(contribution.category_weight, 'department');
  add(contribution.confidence_factor, 'evidence confidence');
  add(contribution.occurrence_factor, 'recurrence');
  add(contribution.jurisdiction_factor, 'jurisdiction match');
  add(contribution.context_factor, 'scene context');
  add(contribution.mitigation_factor, 'adopted mitigation');
  if (Number(contribution.lead_time_surcharge) > 0) {
    factors.push(`lead time +${contribution.lead_time_surcharge}`);
  }
  return factors;
}

/**
 * Builds the full view model: one row per dependency, in the order the engine
 * applied them, plus the hard stops and the reconstruction check.
 */
export function buildExplanation(brief) {
  const data = brief || {};
  const scorecard = data.scorecard || {};
  const breakdown = scorecard.score_breakdown || null;
  if (!breakdown) return null;

  const depsByElement = new Map(
    (data.assessed_dependencies || []).map((d) => [d.element, d])
  );

  const rows = (breakdown.contributions || []).map((contribution) => {
    const dep = depsByElement.get(contribution.element) || null;
    const basis = classifyBasis(dep);
    return {
      element: contribution.element,
      severity: contribution.severity,
      severityClass: severityClass(contribution.severity),
      basis,
      basisLabel: basisLabel(basis),
      basisNote: basisNote(basis),
      evidenceBacked: basis !== BASIS.INHERENT && basis !== BASIS.UNVERIFIED,
      sharePercent: Math.round(Number(contribution.risk_fraction || 0) * 100),
      penalty: Number(contribution.final_penalty || 0),
      before: Number(contribution.readiness_before ?? 0),
      after: Number(contribution.readiness_after ?? 0),
      rationale: contribution.rationale || '',
      factors: activeFactors(contribution),
      citation: primaryCitation(dep),
      jurisdiction: dep?.jurisdiction_label || null,
      jurisdictionMatch: dep?.jurisdiction_match || 'NONE',
      boundSources: Number(dep?.bound_source_count || 0),
      confidence: dep?.confidence || null,
      scenes: dep?.scene_numbers || [],
      triggers: dep?.trigger_phrases || [],
      mitigationOffered: Boolean(dep?.mitigation_option_exists),
      mitigationAdopted: Boolean(dep?.mitigation_adopted),
    };
  });

  const hardStops = (breakdown.hard_stops || []);
  const hasCeiling = hardStops.some((s) => s.score_cap !== null && s.score_cap !== undefined);
  const criticalCount = rows.filter((r) => r.severity === 'CRITICAL').length;

  // A RED reached by accumulation is not a blocker, and the panel must say so
  // rather than leaving the counts row to contradict the headline.
  const decisionBasis = hasCeiling || criticalCount ? 'HARD_STOP' : 'CUMULATIVE';

  return {
    startingScore: Number(breakdown.starting_score ?? 100),
    decisionBasis,
    decisionBasisLabel: decisionBasis === 'HARD_STOP'
      ? 'Hard stop — an individual dependency blocks production'
      : 'Cumulative risk — no individual blocker; readiness is the sum of unresolved exposure',
    rows,
    hardStops: (breakdown.hard_stops || []).map((stop) => ({
      ruleId: stop.rule_id,
      reason: stop.reason,
      element: stop.element || null,
      scoreCap: stop.score_cap === null || stop.score_cap === undefined ? null : Number(stop.score_cap),
      // A ceiling changes the number; a verdict constraint only changes the call.
      affectsScore: stop.score_cap !== null && stop.score_cap !== undefined,
    })),
    ceilingAdjustment: Number(breakdown.ceiling_adjustment || 0),
    floorApplied: Boolean(breakdown.floor_applied),
    finalScore: Number(breakdown.final_score),
    reconstructed: reconstructScore(breakdown),
    reconstructionHolds: reconstructionHolds(breakdown),
    formulaVersion: breakdown.formula_version || '',
    jurisdiction: rows.find((r) => r.jurisdiction)?.jurisdiction || null,
  };
}
