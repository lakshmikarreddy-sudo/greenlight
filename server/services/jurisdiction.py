"""Resolve a screenplay location into a filming jurisdiction.

Evidence is only meaningful if it comes from the authority that actually
governs the shoot. Before this module existed the research queries carried no
place at all, so a Norwegian Arctic scene and a Georgia street scene were both
answered by the same Texas film-office page.

The gazetteer is deliberately data-driven and open: unknown locations resolve
to an UNKNOWN jurisdiction rather than being guessed at, and an unknown
jurisdiction weakens evidence rather than inventing authority.
"""

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class Jurisdiction(BaseModel):
    """Where a scene is shot, and who regulates filming there."""

    city: Optional[str] = Field(default=None, description="City or locality, when identifiable")
    region: Optional[str] = Field(default=None, description="State, province or territory")
    country: Optional[str] = Field(default=None, description="Country name")
    country_code: Optional[str] = Field(default=None, description="ISO-3166 alpha-2, when known")
    authority_domains: List[str] = Field(default_factory=list, description="Domains treated as governing authorities here")
    search_terms: List[str] = Field(default_factory=list, description="Terms that qualify a research query to this place")
    resolved: bool = Field(default=False, description="False when the location could not be placed")

    @property
    def label(self) -> str:
        parts = [p for p in (self.city, self.region, self.country) if p]
        return ", ".join(parts) if parts else "Unknown jurisdiction"

    def matches_text(self, text: str) -> bool:
        """True when text mentions this place by name.

        Word-anchored on purpose. A bare substring test let the two-letter code
        "NO" match inside "notify", so a Texas page satisfied a Norwegian
        jurisdiction check. Country codes are excluded entirely: they are far
        too collision-prone to prove locality.
        """
        low = (text or "").lower()
        for term in (self.city, self.region, self.country):
            if not term:
                continue
            if re.search(r"\b" + re.escape(term.lower()) + r"\b", low):
                return True
        return False


UNKNOWN = Jurisdiction(resolved=False, search_terms=[])


#: (matching tokens) -> jurisdiction. Tokens are matched against the slugline
#: location, longest-token-first, so "BROOKLYN BRIDGE" resolves before "BROOKLYN".
_GAZETTEER: List[Tuple[Tuple[str, ...], Dict]] = [
    (
        ("svalbard", "spitsbergen", "longyearbyen"),
        dict(
            city="Longyearbyen", region="Svalbard", country="Norway", country_code="NO",
            authority_domains=["sysselmesteren.no", "regjeringen.no", "npolar.no", "lovdata.no"],
            search_terms=["Svalbard", "Governor of Svalbard", "Sysselmesteren", "Norway"],
        ),
    ),
    (
        ("brooklyn bridge", "manhattan", "brooklyn", "queens", "bronx", "new york city", "nyc"),
        dict(
            city="New York City", region="New York", country="United States", country_code="US",
            authority_domains=["nyc.gov", "faa.gov", "dot.ny.gov", "ny.gov"],
            search_terms=["New York City", "NYC Mayor's Office of Media and Entertainment", "New York"],
        ),
    ),
    (
        ("savannah", "chatham county"),
        dict(
            city="Savannah", region="Georgia", country="United States", country_code="US",
            authority_domains=["savannahga.gov", "georgia.org", "dps.georgia.gov", "atf.gov"],
            search_terms=["Savannah Georgia", "City of Savannah film office", "Georgia"],
        ),
    ),
    (
        ("los angeles", "hollywood", "burbank", "santa monica"),
        dict(
            city="Los Angeles", region="California", country="United States", country_code="US",
            authority_domains=["filmla.com", "ca.gov", "lacity.org", "faa.gov"],
            search_terms=["Los Angeles", "FilmLA", "California"],
        ),
    ),
    (
        ("london", "westminster", "camden", "soho"),
        dict(
            city="London", region="England", country="United Kingdom", country_code="GB",
            authority_domains=["filmlondon.org.uk", "gov.uk", "caa.co.uk"],
            search_terms=["London", "Film London", "United Kingdom"],
        ),
    ),
    (
        ("paris", "ile-de-france"),
        dict(
            city="Paris", region="Île-de-France", country="France", country_code="FR",
            authority_domains=["paris.fr", "cnc.fr", "service-public.fr"],
            search_terms=["Paris", "France", "CNC"],
        ),
    ),
    (
        ("tokyo", "shibuya", "shinjuku"),
        dict(
            city="Tokyo", country="Japan", country_code="JP",
            authority_domains=["metro.tokyo.lg.jp", "go.jp"],
            search_terms=["Tokyo", "Japan"],
        ),
    ),
    (
        ("iceland", "reykjavik"),
        dict(
            city="Reykjavik", country="Iceland", country_code="IS",
            authority_domains=["government.is", "samgongustofa.is"],
            search_terms=["Iceland", "Reykjavik"],
        ),
    ),
    (
        ("new orleans", "louisiana"),
        dict(
            city="New Orleans", region="Louisiana", country="United States", country_code="US",
            authority_domains=["nola.gov", "louisianaentertainment.gov"],
            search_terms=["New Orleans", "Louisiana"],
        ),
    ),
    (
        ("atlanta",),
        dict(
            city="Atlanta", region="Georgia", country="United States", country_code="US",
            authority_domains=["atlantaga.gov", "georgia.org"],
            search_terms=["Atlanta", "Georgia"],
        ),
    ),
]

#: Domains that regulate a whole country regardless of the city.
NATIONAL_AUTHORITY_DOMAINS: Dict[str, List[str]] = {
    "US": ["faa.gov", "atf.gov", "osha.gov", "nps.gov", "uscg.mil", "noaa.gov"],
    "NO": ["luftfartstilsynet.no", "sysselmesteren.no", "lovdata.no"],
    "GB": ["caa.co.uk", "hse.gov.uk"],
    "FR": ["ecologie.gouv.fr"],
}


#: Place names used only to detect that a source is about somewhere else.
#: Separate from the gazetteer, which lists places we can research *for*.
CONFLICT_PLACES = frozenset(
    {
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
        "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
        "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
        "maine", "maryland", "massachusetts", "michigan", "minnesota",
        "mississippi", "missouri", "montana", "nebraska", "nevada",
        "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
        "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
        "rhode island", "south carolina", "south dakota", "tennessee", "texas",
        "utah", "vermont", "virginia", "washington", "west virginia",
        "wisconsin", "wyoming",
        "norway", "sweden", "finland", "denmark", "iceland", "canada",
        "australia", "new zealand", "japan", "france", "germany", "spain",
        "italy", "ireland", "united kingdom", "scotland", "wales",
    }
)


def names_conflicting_jurisdiction(text: str, ours: "Jurisdiction") -> bool:
    """True when text is explicitly about a *different* known jurisdiction.

    General-purpose: it consults the gazetteer rather than any scenario. A
    Texas government page is genuine authority — for Texas — so it must not be
    allowed to answer for a Norwegian shoot merely because it discusses the
    same activity.
    """
    if not ours.resolved:
        return False

    # If the source names our own jurisdiction anywhere, it is not "about
    # somewhere else" even if it mentions other places in passing.
    if ours.matches_text(text):
        return False

    low = (text or "").lower()
    ours_names = {n.lower() for n in (ours.city, ours.region, ours.country) if n}

    for name in CONFLICT_PLACES:
        if name in ours_names:
            continue
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            return True
    return False


def resolve_jurisdiction(location_raw: Optional[str], *, fallback_text: str = "") -> Jurisdiction:
    """Resolves a slugline location (plus optional scene text) to a jurisdiction.

    Returns an unresolved jurisdiction rather than guessing when nothing in the
    gazetteer matches: downstream, unresolved means weaker evidence, never
    invented authority.
    """
    haystack = f"{location_raw or ''} {fallback_text or ''}".lower()
    if not haystack.strip():
        return UNKNOWN.model_copy(deep=True)

    best: Optional[Tuple[int, Dict]] = None
    for tokens, payload in _GAZETTEER:
        for token in tokens:
            if token in haystack:
                # Longer tokens are more specific: prefer them.
                if best is None or len(token) > best[0]:
                    best = (len(token), payload)
    if best is None:
        return UNKNOWN.model_copy(deep=True)

    payload = dict(best[1])
    code = payload.get("country_code")
    domains = list(payload.get("authority_domains", []))
    for national in NATIONAL_AUTHORITY_DOMAINS.get(code or "", []):
        if national not in domains:
            domains.append(national)
    payload["authority_domains"] = domains
    payload["resolved"] = True
    return Jurisdiction(**payload)
