"""Bind research evidence to a specific dependency, activity and jurisdiction.

Evidence used to be accepted unconditionally: whatever a generic query returned
became the ground truth for a dependency, so a Norwegian Arctic shoot was
assessed against a Texas prop-weapons page and every signal was extracted from
prose that might have nothing to do with the shoot.

Two rules govern this module:

  * A source contributes signals only if it is *bound* — it must match the
    jurisdiction, be a governing authority, or clearly discuss the activity.
  * Every signal records the source and the verbatim span that produced it, so
    a displayed citation always supports the verdict printed beside it.
"""

import re
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import urlparse

from server.models.research import ResearchResult, SearchSource
from server.services.jurisdiction import Jurisdiction, names_conflicting_jurisdiction

# --- Authority tiers -----------------------------------------------------

TIER_STATUTORY = "STATUTORY"
TIER_REGULATOR = "REGULATOR"
TIER_INDUSTRY = "INDUSTRY_BODY"
TIER_TRADE = "TRADE_PRESS"
TIER_COMMERCIAL = "COMMERCIAL"
TIER_UNKNOWN = "UNKNOWN"

#: Weight of a tier when deciding evidence confidence. A government rule page
#: and a drone retailer's blog must never carry equal weight.
TIER_RANK: Dict[str, int] = {
    TIER_STATUTORY: 5,
    TIER_REGULATOR: 4,
    TIER_INDUSTRY: 3,
    TIER_TRADE: 2,
    TIER_COMMERCIAL: 1,
    TIER_UNKNOWN: 0,
}

_STATUTORY_SUFFIXES = (".gov", ".gov.uk", ".mil", "europa.eu", ".gouv.fr", ".go.jp", ".gc.ca")
_STATUTORY_TOKENS = ("legislation", "lovdata", "regjeringen", "service-public")
_REGULATOR_TOKENS = ("faa.", "caa.", "atf.", "osha.", "hse.", "sysselmesteren", "luftfartstilsynet", "noaa.", "uscg.")
_INDUSTRY_TOKENS = ("csatf.org", "safetyontheset", "bectu", "ia_local", "iatse", "filmlondon", "filmla", "pga.org")
_TRADE_TOKENS = ("variety.com", "hollywoodreporter", "deadline.com", "studiodaily", "ibc.org")


def authority_tier(url: str) -> str:
    """Classifies a source domain by how authoritative it is for regulation."""
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return TIER_UNKNOWN
    if any(host.endswith(s) or s in host for s in _STATUTORY_SUFFIXES) or any(t in host for t in _STATUTORY_TOKENS):
        return TIER_STATUTORY
    if any(t in host for t in _REGULATOR_TOKENS):
        return TIER_REGULATOR
    if any(t in host for t in _INDUSTRY_TOKENS):
        return TIER_INDUSTRY
    if any(t in host for t in _TRADE_TOKENS):
        return TIER_TRADE
    return TIER_COMMERCIAL


# --- Binding -------------------------------------------------------------

MATCH_EXACT = "EXACT"
MATCH_NATIONAL = "NATIONAL"
MATCH_NONE = "NONE"


class BoundSource(NamedTuple):
    """A source that earned the right to contribute signals."""

    index: int
    source: SearchSource
    tier: str
    jurisdiction_match: str
    reason: str
    text: str


def _activity_terms(element: str, hazard_class: Optional[str]) -> List[str]:
    """Distinctive words describing the activity this dependency covers."""
    raw = re.split(r"[^a-z]+", f"{element} {hazard_class or ''}".lower())
    stop = {"and", "or", "the", "of", "a", "an", "near", "work", "at", "practical", ""}
    return [w for w in raw if len(w) > 3 and w not in stop]


def bind_sources(
    result: ResearchResult,
    jurisdiction: Jurisdiction,
    element: str,
    hazard_class: Optional[str] = None,
) -> Tuple[List[BoundSource], str]:
    """Selects the sources that may legitimately inform this dependency.

    Returns the bound sources and the best jurisdiction match achieved. A
    source binds when it names the jurisdiction, is a governing authority for
    it, or unambiguously discusses the activity.
    """
    bound: List[BoundSource] = []
    terms = _activity_terms(element, hazard_class)
    best_match = MATCH_NONE

    for index, source in enumerate(result.sources or []):
        blob = " ".join([source.title or "", source.url or ""] + list(source.excerpts or []))
        low = blob.lower()
        tier = authority_tier(source.url or "")
        host = (urlparse(source.url or "").hostname or "").lower()

        match = MATCH_NONE
        reason = ""

        if jurisdiction.resolved and jurisdiction.matches_text(blob):
            match = MATCH_EXACT
            reason = f"names {jurisdiction.label}"
        elif jurisdiction.resolved and any(host.endswith(d) or d in host for d in jurisdiction.authority_domains):
            match = MATCH_EXACT
            reason = f"governing authority domain for {jurisdiction.label}"
        elif jurisdiction.resolved and jurisdiction.country and jurisdiction.country.lower() in low:
            match = MATCH_NATIONAL
            reason = f"national scope for {jurisdiction.country}"
        elif not jurisdiction.resolved and tier in (TIER_STATUTORY, TIER_REGULATOR):
            # Only when we do not know where the shoot is may a government
            # source stand in generically. Once the jurisdiction is known,
            # being a .gov domain proves nothing: gov.texas.gov is statutory
            # and still has no authority over a Norwegian shoot.
            match = MATCH_NATIONAL
            reason = "statutory or regulator source, shoot jurisdiction unknown"

        # A source that is explicitly about another jurisdiction is authority
        # there, not here, however well it matches the activity.
        if match == MATCH_NONE and names_conflicting_jurisdiction(blob, jurisdiction):
            continue

        activity_hits = [t for t in terms if t in low]
        if match == MATCH_NONE:
            # A non-jurisdictional source may still bind on the activity, but
            # only as unlocated evidence.
            if len(activity_hits) >= 2 and tier in (TIER_STATUTORY, TIER_REGULATOR, TIER_INDUSTRY):
                reason = f"authoritative source discussing {', '.join(activity_hits[:2])}"
            else:
                continue
        elif not activity_hits:
            # Right place, wrong subject.
            continue

        bound.append(
            BoundSource(
                index=index,
                source=source,
                tier=tier,
                jurisdiction_match=match,
                reason=reason,
                text=blob,
            )
        )
        if _match_rank(match) > _match_rank(best_match):
            best_match = match

    return bound, best_match


def _match_rank(match: str) -> int:
    return {MATCH_EXACT: 2, MATCH_NATIONAL: 1, MATCH_NONE: 0}[match]


def find_blocker(
    bound: List["BoundSource"],
    blocker_vocab: Sequence[str],
    *,
    min_tier: int = 0,
) -> Optional[Tuple["BoundSource", str]]:
    """Finds evidence that this activity is barred pending an exemption.

    Requires all three, from one governing source: a stated prohibition, the
    activity's own vocabulary nearby, and an exemption instrument. Anything
    less is permitting friction or a mandatory control, not a blocker.
    """
    for source in sorted(bound, key=lambda b: (-TIER_RANK[b.tier], -_match_rank(b.jurisdiction_match))):
        if TIER_RANK[source.tier] < min_tier:
            continue

        # The exemption pathway is looked for across the whole governing
        # document, not the same paragraph: a fire authority states the ban in
        # one section and the permit route in another, and both are still that
        # authority speaking about this activity.
        has_instrument = any(
            re.search(p, source.text, re.IGNORECASE) for p in _EXEMPTION_INSTRUMENT_PATTERNS
        )
        if not has_instrument:
            continue

        for pattern in _PROHIBITION_PATTERNS:
            for m in re.finditer(pattern, source.text, re.IGNORECASE):
                start = max(0, m.start() - 200)
                end = min(len(source.text), m.end() + 200)
                window = source.text[start:end]
                if not any(t in window.lower() for t in blocker_vocab):
                    continue
                return source, window.strip()
    return None


# --- Signal extraction with provenance -----------------------------------

#: A prohibition must be *stated*. "Waiver" on its own is not a statement --
#: it appears in navigation menus, form names and boilerplate.
_PROHIBITION_PATTERNS = (
    r"\bprohibit(?:ed|s|ion|ions)?\b",
    r"\bban(?:ned)?\b",
    r"\bban\s+on\b",
    r"\bunlawful\b",
    r"\billegal\b",
    r"\bnot\s+(?:be\s+)?permitted\b",
    r"\bnot\s+allowed\b",
    r"\bmay\s+not\b",
    r"\bshall\s+not\b",
    r"\bno[- ]fly\b",
    r"\bstrictly\s+restricted\b",
    r"\brestricted\s+airspace\b",
)

#: An exemption instrument is what separates a gating blocker from a control.
#: "Prohibited without fall protection" is a control you adopt; "prohibited
#: without a waiver" is an authorisation you must be granted.
_EXEMPTION_INSTRUMENT_PATTERNS = (
    r"(?<!liability )\bwaivers?\b",
    r"\bauthoriz(?:ation|ations)\b",
    r"\bauthoris(?:ation|ations)\b",
    r"\bexemptions?\b",
    r"\bvariance\b",
    r"\bspecial\s+permits?\b",
    r"\bcertificate\s+of\s+authoriz",
)

_PERMITTING_PATTERNS = (
    r"\bpermits?\b",
    r"\bpermitting\b",
    r"\blicens(?:e|es|ing)\b",
    r"\binsurance\b",
    r"\bmandatory\b",
    r"\bprior\s+approval\b",
    r"\bnotification\b",
)

_SUPERVISION_PATTERNS = (
    r"\bcertified\b",
    r"\bqualified\b",
    r"\bfire\s+marshal\b",
    r"\barmou?rer\b",
    r"\bsafety\s+(?:officer|supervisor|coordinator)\b",
    r"\bpyrotechnician\b",
    r"\blicensed\s+operator\b",
    r"\bstandby\b",
)

_SUBSTITUTION_PATTERNS = (
    r"\bcgi\b",
    r"\bvisual\s+effects\b",
    r"\bvfx\b",
    r"\bdigital\s+(?:double|replacement|set)\b",
    r"\bsimulat(?:ed|ion)\b",
)

#: A number of days only counts as a statutory lead time when it sits next to
#: application language. "15 days" inside a safety bulletin is not a lead time.
_LEAD_TIME_PATTERN = re.compile(
    r"(?:(?:at\s+least|minimum\s+of|no\s+later\s+than|within|allow)\s+)?"
    r"\b(\d{1,3})\s*(?:business\s+|working\s+|calendar\s+)?days?\b"
    r"(?:\s*(?:in\s+advance|prior|before|advance\s+notice|processing|lead\s+time))?",
    re.IGNORECASE,
)
_LEAD_TIME_CONTEXT = re.compile(
    r"(permit|licen|applicat|waiver|submit|approval|advance|notice|lead\s+time|processing)",
    re.IGNORECASE,
)


def _first_match(
    patterns: Sequence[str],
    bound: List[BoundSource],
    *,
    min_tier: int = 0,
    require_terms: Optional[Sequence[str]] = None,
) -> Optional[Tuple[BoundSource, str]]:
    """Highest-authority source that matches, with the span it matched.

    ``min_tier`` refuses claims from sources too weak to make them: a blocker
    assertion must come from a statute or a regulator, never a retailer's blog.
    ``require_terms`` additionally demands that the matched window actually
    discusses the activity, so generic legal boilerplate on a permit page
    cannot escalate an unrelated dependency.
    """
    for source in sorted(bound, key=lambda b: (-TIER_RANK[b.tier], -_match_rank(b.jurisdiction_match))):
        if TIER_RANK[source.tier] < min_tier:
            continue
        for pattern in patterns:
            for m in re.finditer(pattern, source.text, re.IGNORECASE):
                start = max(0, m.start() - 160)
                end = min(len(source.text), m.end() + 160)
                window = source.text[start:end]
                if require_terms and not any(t in window.lower() for t in require_terms):
                    continue
                return source, window.strip()
    return None


def extract_lead_time(bound: List[BoundSource]) -> Optional[Tuple[BoundSource, int, str]]:
    """Statutory lead time, only where application context supports it."""
    best: Optional[Tuple[BoundSource, int, str]] = None
    for source in bound:
        for m in _LEAD_TIME_PATTERN.finditer(source.text):
            days = int(m.group(1))
            if not 1 <= days <= 365:
                continue
            window = source.text[max(0, m.start() - 120): m.end() + 120]
            if not _LEAD_TIME_CONTEXT.search(window):
                continue
            if best is None or days > best[1]:
                best = (source, days, window.strip())
    return best


def confidence_for(bound: List[BoundSource], jurisdiction_match: str) -> str:
    """Confidence reflects authority and locality, not merely source count."""
    if not bound:
        return "LOW"
    top = max(TIER_RANK[b.tier] for b in bound)
    if top >= TIER_RANK[TIER_REGULATOR] and jurisdiction_match == MATCH_EXACT:
        return "HIGH"
    if top >= TIER_RANK[TIER_INDUSTRY] and jurisdiction_match in (MATCH_EXACT, MATCH_NATIONAL):
        return "MEDIUM"
    if top <= TIER_RANK[TIER_COMMERCIAL]:
        return "LOW"
    return "MEDIUM"
