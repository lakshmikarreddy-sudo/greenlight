"""Production hazard catalogue driving dependency extraction.

The previous extractor recognised seven bare substrings, so an Arctic glacier
sequence produced exactly one dependency ("Firearms") and missed the cold, the
crevasse field, the wildlife and the remoteness that actually govern the shoot.

Each rule here is a standard production hazard class with a word-anchored
detector, a department, and the research objective a line producer would
actually raise. Rules are generic: nothing keys off a scenario id or title.
"""

import re
from typing import Dict, List, NamedTuple, Optional, Pattern, Tuple

from server.models.screenplay import DependencyCategory, RiskLevel


class HazardRule(NamedTuple):
    """One detectable production hazard."""

    hazard_class: str
    element: str
    category: DependencyCategory
    baseline_risk: RiskLevel
    description: str
    research_objective: str
    #: Query fragments; the jurisdiction is appended at search time.
    query_templates: Tuple[str, ...]
    patterns: Tuple[str, ...]
    #: Terms that must also appear for the rule to fire (context guard).
    requires_any: Tuple[str, ...] = ()
    #: Vocabulary that would indicate *this* activity is legally barred or
    #: gated behind an exemption. A prohibition word near generic permit prose
    #: is not a blocker; a prohibition word near these terms is.
    blocker_terms: Tuple[str, ...] = ()
    #: Extra queries raised only when the scene carries a given context flag,
    #: e.g. a night shoot asking specifically about night-operation waivers.
    context_templates: Tuple[Tuple[str, str], ...] = ()
    #: What a line producer actually does about this hazard. Without it every
    #: HIGH dependency received the same "engage a certified supervisor" text,
    #: which is useless advice for extreme cold or a crevasse field.
    mitigation_template: str = ""


def _rx(pattern: str) -> Pattern:
    return re.compile(pattern, re.IGNORECASE)


HAZARD_RULES: Tuple[HazardRule, ...] = (
    HazardRule(
        hazard_class="AVIATION_UAS",
        element="Low-altitude Drone Flight",
        category=DependencyCategory.PERMITS_AND_LEGAL,
        baseline_risk=RiskLevel.RED,
        description="Uncrewed aircraft operation requires civil aviation authorisation and, over people or moving vehicles, an explicit waiver.",
        research_objective="Verify civil aviation authority rules and waivers for uncrewed aircraft filming",
        query_templates=(
            "drone filming authorization and waiver requirements {jurisdiction}",
            "Part 107 waiver operations over people and moving vehicles {jurisdiction}",
            "low altitude drone flight restricted airspace rules {jurisdiction}",
        ),
        patterns=(r"\bdrones?\b", r"\buav\b", r"\bfpv\b", r"\bquadcopter\b", r"\bunmanned aircraft\b"),
        blocker_terms=(
            "no-fly", "no fly", "airspace", "part 107", "107.29", "107.39",
            "waiver", "authorization", "unmanned aircraft", "drone", "uas",
            "over people", "moving vehicles", "night operation",
        ),
        context_templates=(
            ("night_work", "Part 107 night operations waiver civil twilight anti-collision lighting {jurisdiction}"),
            ("public_access", "drone flight over people and crowds authorization category {jurisdiction}"),
        ),
        mitigation_template=(
            "Secure the civil aviation authorisation or waiver for flight over people and vehicles, appoint a licensed remote pilot and visual observer, and file the airspace request before the shoot date."
        ),
    ),
    HazardRule(
        hazard_class="PYROTECHNICS",
        element="Pyrotechnic / Practical Explosion",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="Practical explosions and pyrotechnic effects require a licensed pyrotechnician, fire authority permit and an exclusion zone.",
        research_objective="Verify fire authority pyrotechnic permitting, licensed operator and exclusion zone requirements",
        query_templates=(
            "film pyrotechnics permit fire marshal requirements {jurisdiction}",
            "licensed pyrotechnician special effects explosion regulations {jurisdiction}",
        ),
        patterns=(r"\bexplosions?\b", r"\bpyro(?:technics?|technic)?\b", r"\bfireball\b", r"\bdetonat\w*\b", r"\bgrenades?\b", r"\bblast\b"),
        blocker_terms=("burn ban", "pyrotechnic", "explosive", "blasting", "fireworks"),
        context_templates=(
            ("public_access", "pyrotechnic exclusion zone distance from public spectators {jurisdiction}"),
            ("night_work", "night pyrotechnic effects noise and fire watch rules {jurisdiction}"),
        ),
        mitigation_template=(
            "Engage a licensed pyrotechnician, obtain the fire authority permit, agree the exclusion zone and charge sizes on a walked-through plot, and hold fire suppression on standby."
        ),
    ),
    HazardRule(
        hazard_class="FIREARMS",
        element="Firearms / Weapons",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="Weapons on set require a qualified armourer, secure storage, and in most jurisdictions a permit and police notification.",
        research_objective="Verify armourer, storage and permit requirements for firearms use on set",
        query_templates=(
            "film production firearms armourer permit requirements {jurisdiction}",
            "blank firing weapons on set safety regulations {jurisdiction}",
        ),
        patterns=(r"\bguns?\b", r"\bgunfire\b", r"\brifles?\b", r"\bpistols?\b", r"\bweapons?\b", r"\bfirearms?\b", r"\bshotguns?\b"),
        blocker_terms=("firearm", "weapon", "blank", "ammunition", "discharge"),
        context_templates=(
            ("public_access", "discharging blank firearms in public space notification police {jurisdiction}"),
        ),
        mitigation_template=(
            "Appoint a qualified armourer with sole custody of the weapons, use secure lockable storage, run a cold-weapon check before each take, and complete any police notification the jurisdiction requires."
        ),
    ),
    HazardRule(
        hazard_class="EXTREME_COLD",
        element="Extreme Cold / Sub-Zero Exposure",
        category=DependencyCategory.WEATHER_AND_ENVIRONMENT,
        baseline_risk=RiskLevel.RED,
        description="Sustained sub-zero exposure drives frostbite and hypothermia risk, mandates warming rotations, medical standby and cold-rated equipment.",
        research_objective="Verify occupational cold exposure limits, warming rotation and medical standby requirements for crew",
        query_templates=(
            "film crew cold weather safety requirements sub-zero {jurisdiction}",
            "occupational hypothermia frostbite exposure limits outdoor work {jurisdiction}",
        ),
        patterns=(
            r"-\s?\d{1,2}\s?°?\s?c\b", r"\bsub-?zero\b", r"\barctic\b", r"\bblizzard\b",
            r"\bwhiteout\b", r"\bfrostbite\b", r"\bhypothermia\b", r"\bpermafrost\b",
        ),
        blocker_terms=("exposure limit", "cold stress", "temperature"),
        mitigation_template=(
            "Publish a cold-exposure plan with timed warming rotations and heated shelter, issue cold-rated crew and camera equipment, and place medical monitoring on set for frostbite and hypothermia."
        ),
    ),
    HazardRule(
        hazard_class="ICE_AND_CREVASSE",
        element="Glacier / Sea Ice Travel",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="Movement over glacier, crevasse fields or sea ice requires roped travel, ice assessment and qualified mountain or ice safety leadership.",
        research_objective="Verify glacier and sea ice travel safety requirements and qualified guide mandates",
        query_templates=(
            "glacier crevasse field filming safety requirements guide {jurisdiction}",
            "sea ice travel safety assessment regulations {jurisdiction}",
        ),
        patterns=(r"\bcrevasse\w*\b", r"\bglaciers?\b", r"\bsea ice\b", r"\bice floe\b", r"\bmoraine\b", r"\bfragile ice\b"),
        blocker_terms=("glacier", "sea ice", "crevasse", "ice travel"),
        mitigation_template=(
            "Contract qualified ice or mountain leadership, complete a route and ice-thickness assessment on the shoot day, and run roped travel with crevasse rescue equipment and a briefed team."
        ),
    ),
    HazardRule(
        hazard_class="REMOTE_OPERATIONS",
        element="Remote Location / Medical Evacuation",
        category=DependencyCategory.LOCATIONS_AND_ACCESS,
        baseline_risk=RiskLevel.RED,
        description="Filming beyond routine emergency response requires an evacuation plan, satellite communications redundancy and on-site medical capability.",
        research_objective="Verify remote location medevac, communications redundancy and permit requirements",
        query_templates=(
            "remote location filming medical evacuation plan requirements {jurisdiction}",
            "wilderness expedition filming permit and safety requirements {jurisdiction}",
        ),
        patterns=(
            r"\bstranded\b", r"\bsatellite relay\b", r"\bsatellite phone\b", r"\bmedevac\b",
            r"\bexpedition\b", r"\bremote\b", r"\bno signal\b", r"\bwent dark\b",
        ),
        blocker_terms=("remote", "expedition", "field activity", "search and rescue", "insurance"),
        mitigation_template=(
            "Write and rehearse a medical evacuation plan with a named receiving facility, carry redundant satellite communications, and place a qualified medic with trauma capability on location."
        ),
    ),
    HazardRule(
        hazard_class="DANGEROUS_WILDLIFE",
        element="Dangerous Wildlife Encounter",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="Filming where large predators are present requires trained wildlife watch, deterrent protocol and statutory distance rules.",
        research_objective="Verify wildlife protection rules, mandatory deterrents and safe distance requirements",
        query_templates=(
            "wildlife encounter safety rules film production predator {jurisdiction}",
            "protected species minimum distance filming regulations {jurisdiction}",
        ),
        patterns=(
            r"\bpolar bears?\b", r"\bbears?\b", r"\bpredators?\b", r"\bwolves?\b",
            r"\bapex (?:arctic )?predator\b", r"\bwildlife\b",
        ),
        blocker_terms=("polar bear", "wildlife", "disturb", "protected species", "distance"),
        mitigation_template=(
            "Post a trained wildlife watch with an agreed deterrent protocol, hold the statutory minimum distance, and brief every crew member on the stop-work and withdrawal procedure."
        ),
    ),
    HazardRule(
        hazard_class="MARINE_AND_WATER",
        element="Water / Marine Filming",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.YELLOW,
        description="Work on or above open water requires standby rescue craft, water safety personnel and immersion protection.",
        research_objective="Verify water safety, standby rescue craft and marine authority notification requirements",
        query_templates=(
            "filming over open water safety standby rescue boat requirements {jurisdiction}",
            "marine authority film permit navigable waters {jurisdiction}",
        ),
        patterns=(r"\bopen water\b", r"\brivers?\b", r"\bocean\b", r"\bharbou?r\b", r"\bfjord\b", r"\bboats?\b", r"\bunderwater\b", r"\blakes?\b"),
        blocker_terms=("navigable", "marine", "vessel", "waterway", "coast guard"),
        mitigation_template=(
            "Station a standby rescue craft with qualified water-safety personnel, issue immersion protection to anyone working over water, and confirm the marine authority notification."
        ),
    ),
    HazardRule(
        hazard_class="TRAFFIC_AND_VEHICLES",
        element="Traffic / Roadway Filming",
        category=DependencyCategory.LOCATIONS_AND_ACCESS,
        baseline_risk=RiskLevel.YELLOW,
        description="Filming that interacts with live traffic requires a road authority permit, police traffic control and a lane closure plan.",
        research_objective="Verify road authority permits and police traffic control requirements for roadway filming",
        query_templates=(
            "road closure film permit traffic control requirements {jurisdiction}",
            "filming on bridge or highway authority approval {jurisdiction}",
        ),
        patterns=(r"\btraffic\b", r"\broadway\b", r"\bhighway\b", r"\bfreeway\b", r"\bbridges?\b", r"\bbox trucks?\b", r"\bmoving vehicles?\b"),
        blocker_terms=("lane closure", "roadway closure", "bridge", "highway", "traffic control"),
        context_templates=(
            ("night_work", "overnight lane closure filming approval {jurisdiction}"),
        ),
        mitigation_template=(
            "Obtain the road authority permit, book police traffic control, publish a lane-closure and pedestrian diversion plan, and notify affected residents and businesses."
        ),
    ),
    HazardRule(
        hazard_class="VEHICLE_STUNT",
        element="Vehicle Stunt / High-Speed Action",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="High-speed or precision vehicle action requires a stunt coordinator, precision drivers and a closed course.",
        research_objective="Verify stunt driving, closed course and coordinator certification requirements",
        query_templates=(
            "vehicle stunt filming safety closed course requirements {jurisdiction}",
            "precision driver stunt coordinator certification film {jurisdiction}",
        ),
        patterns=(r"\b\d{2,3}\s?mph\b", r"\bhigh-?speed\b", r"\bcar chase\b", r"\bsnowmobiles?\b", r"\barmored transport\b", r"\bpursuit\b"),
        blocker_terms=("stunt", "closed course", "speed", "precision driving"),
        mitigation_template=(
            "Engage a stunt coordinator and precision drivers, run the action on a closed course with a rehearsed sequence, and confirm the vehicle preparation and insurance riders."
        ),
    ),
    HazardRule(
        hazard_class="WORKING_AT_HEIGHT",
        element="Work at Height / Fall Exposure",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="Crew positioned above ground level requires fall arrest, rescue plan and a competent rigging supervisor.",
        research_objective="Verify fall protection, rigging and rescue plan requirements for elevated crew positions",
        query_templates=(
            "fall protection requirements film crew working at height {jurisdiction}",
            "rigging gantry safety regulations film production {jurisdiction}",
        ),
        patterns=(r"\bgantry\b", r"\bscaffold\w*\b", r"\bcatwalk\b", r"\brooftops?\b", r"\bhigh fall\b", r"\bsuspension cables?\b", r"\bgirders?\b"),
        blocker_terms=("fall protection", "height", "rigging", "scaffold"),
        mitigation_template=(
            "Appoint a competent rigging supervisor, fit fall-arrest for anyone above ground level, and put a written rescue-at-height plan in place before the position is used."
        ),
    ),
    HazardRule(
        hazard_class="HERITAGE_PROPERTY",
        element="Historic / Heritage Property",
        category=DependencyCategory.LOCATIONS_AND_ACCESS,
        baseline_risk=RiskLevel.YELLOW,
        description="Filming at protected heritage sites requires conservation authority consent and restricts effects, rigging and heat sources.",
        research_objective="Verify heritage conservation consent and effects restrictions at protected sites",
        query_templates=(
            "historic district filming permit heritage conservation restrictions {jurisdiction}",
            "protected landmark filming special effects restrictions {jurisdiction}",
        ),
        patterns=(
            r"\bhistoric(?:al)? (?:district|square|mansions?|townhouses?)\b", r"\bheritage\b",
            r"\blandmarks?\b", r"\bcentury-old\b", r"\b19th-century\b", r"\bcobblestone\b",
        ),
        blocker_terms=("landmark", "heritage", "historic district", "conservation"),
        mitigation_template=(
            "Obtain conservation authority consent, agree the protection measures for fabric and planting, and confirm which effects, rigging and heat sources are excluded on site."
        ),
    ),
    HazardRule(
        hazard_class="WILDFIRE_RISK",
        element="Open Flame Near Combustible Vegetation",
        category=DependencyCategory.SAFETY_AND_STUNTS,
        baseline_risk=RiskLevel.RED,
        description="Flame or ember-producing effects near dry vegetation or timber require fire watch, suppression standby and burn-ban verification.",
        research_objective="Verify fire watch, suppression standby and burn ban rules for open flame effects",
        query_templates=(
            "open flame special effects fire watch burn ban rules {jurisdiction}",
            "fire suppression standby requirements filming vegetation {jurisdiction}",
        ),
        patterns=(r"\bdry timber\b", r"\bembers?\b", r"\bbrush fire\b", r"\bwildfire\b", r"\bspanish moss\b", r"\bdry brush\b"),
        requires_any=("fire", "flame", "explos", "pyro", "ember", "ignit", "blast"),
        blocker_terms=("burn ban", "open flame", "fire danger", "wildfire", "vegetation"),
        mitigation_template=(
            "Verify no active burn ban covers the shoot date, hold a dedicated fire watch with suppression standby, and clear and wet down combustible vegetation inside the effect radius."
        ),
    ),
    HazardRule(
        hazard_class="MINORS",
        element="Minor / Child Performer",
        category=DependencyCategory.CAST_AND_LABOR,
        baseline_risk=RiskLevel.RED,
        description="Engaging performers under 18 triggers work-hour limits, guardian and tutor requirements and a child performance permit.",
        research_objective="Verify child performer permits, working hour limits and guardian requirements",
        query_templates=(
            "child performer work permit hours regulations film {jurisdiction}",
            "minors on set guardian tutor legal requirements {jurisdiction}",
        ),
        patterns=(r"\bchildren?\b", r"\bboys?\b", r"\bgirls?\b", r"\bkids?\b", r"\bteenagers?\b", r"\bminors?\b", r"\btoddlers?\b"),
        blocker_terms=("minor", "child", "work permit", "school hours"),
        mitigation_template=(
            "Obtain the child performance permit, engage the required guardian and on-set tutor, and build the schedule to the statutory working-hour and rest limits."
        ),
    ),
    HazardRule(
        hazard_class="PUBLIC_CROWD",
        element="Public Access / Crowd Control",
        category=DependencyCategory.LOCATIONS_AND_ACCESS,
        baseline_risk=RiskLevel.YELLOW,
        description="Filming in publicly accessible space requires perimeter control, public notification and often police support.",
        research_objective="Verify public space filming permits, perimeter control and notification requirements",
        query_templates=(
            "public space filming permit crowd control notification {jurisdiction}",
            "street closure public notification film production {jurisdiction}",
        ),
        patterns=(r"\bcrowds?\b", r"\bbystanders?\b", r"\bpedestrians?\b", r"\bpublic square\b", r"\bperimeter\b", r"\bspectators?\b"),
        blocker_terms=("street closure", "public assembly", "crowd"),
        mitigation_template=(
            "Establish a controlled perimeter with marshals, publish public notification in advance, and agree police or security support for the affected area."
        ),
    ),
)


# --- Scene-level production context -------------------------------------

NIGHT_PATTERNS = (r"\bnight\b", r"\bdusk\b", r"\btwilight\b", r"\bafter dark\b", r"\bnocturnal\b")
ADVERSE_WEATHER_PATTERNS = (r"\brain\b", r"\bstorm\b", r"\bblizzard\b", r"\bfog\b", r"\bwind\b", r"\bsnow\b", r"\bwhiteout\b", r"\bslick\w*\b")
PUBLIC_PATTERNS = (r"\bsquare\b", r"\bstreet\b", r"\bpublic\b", r"\bsidewalk\b", r"\bcurb\b", r"\broadway\b", r"\bpark\b")


def _any(patterns: Tuple[str, ...], text: str) -> bool:
    return any(_rx(p).search(text) for p in patterns)


def detect_context(scene_text: str, time_of_day: str) -> Dict[str, bool]:
    """Scene-level facts that modify how severely a hazard should be treated."""
    blob = f"{scene_text} {time_of_day}"
    return {
        "night_work": _any(NIGHT_PATTERNS, blob),
        "adverse_weather": _any(ADVERSE_WEATHER_PATTERNS, blob),
        "public_access": _any(PUBLIC_PATTERNS, blob),
    }


def detect_hazards(scene_text: str) -> List[Tuple[HazardRule, List[str]]]:
    """Returns each hazard rule that fires, with the phrases that triggered it.

    Recording the matched phrases is what makes an extraction auditable: every
    dependency can point at the words in the screenplay that produced it.
    """
    fired: List[Tuple[HazardRule, List[str]]] = []
    low = scene_text.lower()

    for rule in HAZARD_RULES:
        matches: List[str] = []
        for pattern in rule.patterns:
            for m in _rx(pattern).finditer(scene_text):
                phrase = m.group(0).strip()
                if phrase and phrase.lower() not in {x.lower() for x in matches}:
                    matches.append(phrase)
        if not matches:
            continue
        if rule.requires_any and not any(term in low for term in rule.requires_any):
            continue
        fired.append((rule, matches))

    return fired
