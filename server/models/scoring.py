"""Deterministic readiness-scoring schemas.

The scoring layer exists so that AI and external research identify, research and
describe production dependencies, while the final readiness number is computed
by a pure, auditable function of the assessed dependencies.

Every published score must be reconstructible from its own ``ScoreBreakdown``:

    starting_score - sum(contribution.final_penalty)  ->  raw_total
    raw_total, after hard-stop caps and the floor     ->  final_score
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


#: Bumped whenever weights or rules change, so an archived brief stays readable.
FORMULA_VERSION = "v2.1"


class Severity(str, Enum):
    """Magnitude of a single dependency's production risk.

    Derived from evidence signals; never authored directly by a model.
    """

    CRITICAL = "CRITICAL"   # Statutory blocker or prohibition-grade exposure
    HIGH = "HIGH"           # Life-safety operation requiring certified supervision
    MODERATE = "MODERATE"   # Permitting, insurance or scheduling friction
    LOW = "LOW"             # Routine protocol


class EvidenceConfidence(str, Enum):
    """How much weight the evidence behind a signal set can bear."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RiskContribution(BaseModel):
    """One dependency's audited contribution to the readiness deduction.

    Carries every factor of the multiplication so a reader can recompute
    ``final_penalty`` by hand.
    """

    element: str = Field(..., description="Dependency this deduction is attributed to")
    category: str = Field(..., description="Dependency category driving the category weight")
    severity: Severity = Field(..., description="Derived severity tier")

    base_penalty: float = Field(..., description="Base risk share for the severity tier, as a fraction of remaining readiness")
    risk_fraction: float = Field(default=0.0, description="Share of remaining readiness this dependency removes")
    readiness_before: int = Field(default=100, description="Readiness immediately before this deduction")
    readiness_after: int = Field(default=100, description="Readiness immediately after this deduction")
    category_weight: float = Field(..., description="Multiplier for the dependency category")
    confidence_factor: float = Field(..., description="Damping applied for weaker evidence")
    occurrence_factor: float = Field(default=1.0, description="Scaling for how many scenes the hazard appears in")
    jurisdiction_factor: float = Field(default=1.0, description="Damping when evidence did not match the shoot's jurisdiction")
    context_factor: float = Field(default=1.0, description="Aggravation from scene facts such as night work or public access")
    mitigation_factor: float = Field(default=1.0, description="Residual reduction when a substitution is confirmed adopted")
    lead_time_surcharge: float = Field(default=0.0, description="Extra points for long statutory lead times")
    severity_capped_by_confidence: bool = Field(default=False, description="True when weak evidence prevented a higher severity")

    final_penalty: int = Field(..., description="Points actually deducted from readiness")
    rationale: str = Field(..., description="Plain-language reason a judge can read aloud")
    evidence_url: Optional[str] = Field(default=None, description="Supporting citation, when research produced one")


class HardStop(BaseModel):
    """A deterministic rule that overrides the numeric verdict."""

    rule_id: str = Field(..., description="Stable identifier, e.g. HS-1")
    reason: str = Field(..., description="Why the rule fired, in production terms")
    element: Optional[str] = Field(default=None, description="Dependency that triggered the rule, when specific")
    score_cap: Optional[int] = Field(default=None, description="Upper bound this rule imposes on readiness")


class ScoreBreakdown(BaseModel):
    """Full audit trail for a readiness score."""

    starting_score: int = Field(default=100, description="Readiness before any deductions")
    contributions: List[RiskContribution] = Field(default_factory=list, description="Per-dependency deductions")
    hard_stops: List[HardStop] = Field(default_factory=list, description="Deterministic override rules that fired")
    raw_total: int = Field(..., description="Score after deductions, before caps and floor")
    floor_applied: bool = Field(default=False, description="True when the minimum readiness floor bound the result")
    cap_applied: bool = Field(default=False, description="True when a hard-stop cap bound the result")
    ceiling_adjustment: int = Field(default=0, description="Readiness removed by a hard-stop ceiling, over and above dependency deductions")
    final_score: int = Field(..., ge=0, le=100, description="Published readiness score")
    formula_version: str = Field(default=FORMULA_VERSION, description="Scoring formula version")

    def explain(self) -> List[str]:
        """Renders the score as the line-by-line answer to 'why this number?'.

        Every arithmetic step is shown, including the hard-stop ceiling and the
        deductions taken against it, so a reader can reproduce ``final_score``
        with a pencil. A cap that silently swallowed the running total was the
        reason an earlier version could print 100, -34, -9, -8 and then 23.
        """
        lines = [f"Starting readiness: {self.starting_score}."]

        for item in self.contributions:
            # Show the risk share as well as the points. Dependencies are
            # applied largest-share first, so a serious hazard considered late
            # removes fewer absolute points; without the share, a reader would
            # mistake ordering for relative importance.
            share = round(item.risk_fraction * 100)
            lines.append(
                f"{item.element} [{item.severity.value}]: removes {share}% of remaining readiness "
                f"= -{item.final_penalty} ({item.readiness_before} -> {item.readiness_after}), "
                f"because of {item.rationale}."
            )

        for stop in self.hard_stops:
            if stop.score_cap is None:
                lines.append(f"Hard stop {stop.rule_id}: {stop.reason} (verdict constraint, no score change).")
            else:
                lines.append(
                    f"Hard stop {stop.rule_id}: {stop.reason}. "
                    f"Readiness ceiling {stop.score_cap} applied."
                )

        if self.ceiling_adjustment:
            lines.append(f"Hard-stop ceiling removed a further {self.ceiling_adjustment}.")
        if self.floor_applied:
            lines.append(f"Readiness floor applied at {self.final_score}.")

        lines.append(f"Final readiness: {self.final_score}.")
        return lines

    def reconstruct(self) -> int:
        """Recomputes the published score from the audit trail alone."""
        total = self.starting_score - sum(c.final_penalty for c in self.contributions)
        total -= self.ceiling_adjustment
        return max(total, self.final_score) if self.floor_applied else total
