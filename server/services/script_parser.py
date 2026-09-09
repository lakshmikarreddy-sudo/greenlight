"""Deterministic screenplay parsing utilities.

Provides ScriptParser with parse_text, parse_fountain and a PDF fallback contract.
Parsing is deterministic and conservative: it never invents facts and raises clear
exceptions on unsupported inputs.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple, Union

from server.models.screenplay import (
    ScreenplayBreakdown,
    Scene,
    Slugline,
    SettingType,
    TimeOfDay,
    ProductionDependency,
    DependencyCategory,
    RiskLevel,
)


class ParseError(Exception):
    """Raised for empty or malformed input."""


class PDFRequiresGeminiError(Exception):
    """Raised when a PDF input cannot be deterministically parsed locally.

    This signals the ADK/Gemini layer to perform native PDF understanding.
    """


class ScriptParser:
    """Deterministic, conservative screenplay parser.

    Usage:
      ScriptParser.parse_text(text)
      ScriptParser.parse_fountain(fountain_text)
      ScriptParser.parse_pdf(path_or_bytes)  # raises PDFRequiresGeminiError
    """

    SLUG_PREFIXES = ("INT.", "EXT.", "INT/EXT.", "I/E.")

    @staticmethod
    def _normalize_slug(raw: str) -> Slugline:
        raw_str = raw.strip()
        upper = raw_str.upper()
        setting = SettingType.UNKNOWN
        if upper.startswith("EXT."):
            setting = SettingType.EXT
        elif upper.startswith("INT."):
            setting = SettingType.INT
        elif upper.startswith("INT/EXT.") or upper.startswith("I/E."):
            setting = SettingType.INT_EXT

        # Split on hyphen for location vs time
        location = raw_str
        tod = TimeOfDay.UNSPECIFIED
        if "-" in raw_str:
            left, right = raw_str.split("-", 1)
            location = left
            rt = right.upper()
            if "NIGHT" in rt:
                tod = TimeOfDay.NIGHT
            elif "DAY" in rt:
                tod = TimeOfDay.DAY
            elif "DAWN" in rt:
                tod = TimeOfDay.DAWN
            elif "DUSK" in rt:
                tod = TimeOfDay.DUSK
            elif "MAGIC" in rt or "GOLDEN" in rt:
                tod = TimeOfDay.MAGIC_HOUR

        # remove slug prefix tokens from location
        for p in ("INT.", "EXT.", "INT/EXT.", "I/E."):
            if location.upper().startswith(p):
                location = location[len(p) :].strip()

        return Slugline(raw=raw_str, setting=setting, location=location.strip(), time_of_day=tod)

    @staticmethod
    def parse_text(text: str, project_title: str = "Untitled") -> ScreenplayBreakdown:
        if text is None:
            raise ParseError("Input is None")
        text = text.strip()
        if not text:
            raise ParseError("Input text is empty")

        lines = [l.rstrip() for l in text.splitlines()]

        scenes: List[Scene] = []
        current_lines: List[str] = []
        current_slug_raw: Optional[str] = None
        scene_index = 0

        def flush_scene():
            nonlocal scene_index, current_lines, current_slug_raw
            if current_slug_raw is None and not current_lines:
                return
            scene_index += 1
            slug = ScriptParser._normalize_slug(current_slug_raw or "EXT. UNKNOWN")
            body = "\n".join(current_lines).strip()
            summary = ScriptParser._generate_summary(body)
            chars = ScriptParser._extract_characters(current_lines)
            props = ScriptParser._extract_physical_elements(body)
            env = ScriptParser._extract_environmental(body)
            deps = ScriptParser._extract_dependencies(
                body, chars, scene_number=scene_index, time_of_day=slug.raw + " " + slug.time_of_day.value
            )
            scene_context = sorted({flag for d in deps for flag in d.context_flags})

            scenes.append(
                Scene(
                    scene_number=scene_index,
                    context_flags=scene_context,
                    slugline=slug,
                    summary=summary,
                    page_count=None,
                    characters=sorted(list(dict.fromkeys(chars))),
                    props_and_wardrobe=sorted(list(dict.fromkeys(props))),
                    stunts_and_sfx=sorted(list(dict.fromkeys([d.element for d in deps if "pyro" in d.element.lower() or "stunt" in d.element.lower() or "explosion" in d.element.lower()]))),
                    environmental_factors=env,
                    dependencies=deps,
                )
            )
            current_lines = []
            current_slug_raw = None

        # Identify sluglines and accumulate scene text
        for raw in lines:
            strip = raw.strip()
            up = strip.upper()
            if any(up.startswith(p) for p in ScriptParser.SLUG_PREFIXES):
                # new scene
                # flush previous
                flush_scene()
                current_slug_raw = strip
            else:
                current_lines.append(strip)

        # end for
        flush_scene()

        if not scenes:
            # No identified sluglines — attempt to treat whole thing as one scene
            slug = ScriptParser._normalize_slug("EXT. UNKNOWN - UNSPECIFIED")
            body = text
            summary = ScriptParser._generate_summary(body)
            chars = ScriptParser._extract_characters(body.splitlines())
            props = ScriptParser._extract_physical_elements(body)
            env = ScriptParser._extract_environmental(body)
            deps = ScriptParser._extract_dependencies(
                body, chars, scene_number=1, time_of_day=slug.raw + " " + slug.time_of_day.value
            )
            scene_context = sorted({flag for d in deps for flag in d.context_flags})
            scenes.append(
                Scene(
                    scene_number=1,
                    context_flags=scene_context,
                    slugline=slug,
                    summary=summary,
                    page_count=None,
                    characters=sorted(list(dict.fromkeys(chars))),
                    props_and_wardrobe=sorted(list(dict.fromkeys(props))),
                    stunts_and_sfx=sorted(list(dict.fromkeys([d.element for d in deps if "pyro" in d.element.lower() or "stunt" in d.element.lower() or "explosion" in d.element.lower()]))),
                    environmental_factors=env,
                    dependencies=deps,
                )
            )

        breakdown = ScreenplayBreakdown(
            project_title=project_title,
            author=None,
            screenplay_summary=ScriptParser._compose_overall_summary(scenes),
            total_scenes=len(scenes),
            scenes=scenes,
        )
        return breakdown

    @staticmethod
    def parse_fountain(fountain_text: str, project_title: str = "Untitled Fountain") -> ScreenplayBreakdown:
        # Fountain is plain text with scene headings similar to sluglines; reuse parse_text
        if fountain_text is None:
            raise ParseError("Input is None")
        # Some Fountain writers prefix scene headings with '.' or 'INT.' etc. We'll normalize by stripping leading '.'
        normalized = []
        for line in fountain_text.splitlines():
            if line.startswith('.'):
                normalized.append(line[1:].strip())
            else:
                normalized.append(line)
        return ScriptParser.parse_text("\n".join(normalized), project_title=project_title)

    @staticmethod
    def parse_pdf(path_or_bytes: Union[str, bytes]):
        # We do not parse PDFs locally. Signal that Gemini/ADK must handle this.
        raise PDFRequiresGeminiError("PDF input requires Gemini native understanding (PDF_REQUIRES_GEMINI)")

    # -- heuristic helpers -------------------------------------------------
    @staticmethod
    def _generate_summary(body: str) -> str:
        # Use first 1-3 action lines as a concise summary
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        if not lines:
            return "(No action or dialogue present)"
        snippets = []
        for ln in lines:
            if ln and not ln.isupper():
                snippets.append(ln)
            if len(snippets) >= 3:
                break
        if not snippets:
            snippets = [lines[0]]
        return " ".join(snippets)[:400]

    @staticmethod
    def _extract_characters(lines: List[str]) -> List[str]:
        chars: List[str] = []
        # Character cues are usually uppercase single-line tokens followed by dialogue
        for i, ln in enumerate(lines):
            s = ln.strip()
            if not s:
                continue
            # candidate: all-caps, limited punctuation, short
            if re.fullmatch(r"[A-Z0-9 '\"""\-().,]{1,60}", s) and s.upper() == s:
                # Avoid sluglines
                if any(s.startswith(p) for p in ScriptParser.SLUG_PREFIXES):
                    continue
                # Look ahead for dialogue or parenthetical
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if nxt and not nxt.isupper():
                    # likely a character cue
                    name = s.split('(')[0].strip()
                    # Exclude common scene directions misdetected
                    if len(name) > 0 and len(name) < 60:
                        chars.append(name)
        return chars

    @staticmethod
    def _extract_physical_elements(body: str) -> List[str]:
        found: List[str] = []
        keywords = {
            "drone": "DRONE",
            "fpv": "DRONE",
            "uav": "DRONE",
            "car": "VEHICLE",
            "truck": "VEHICLE",
            "boat": "VEHICLE",
            "motorcycle": "VEHICLE",
            "gun": "WEAPON",
            "rifle": "WEAPON",
            "pistol": "WEAPON",
            "explosion": "SFX_PYRO",
            "pyro": "SFX_PYRO",
            "fire": "SFX_PRACTICAL",
            "smoke": "SFX_PRACTICAL",
            "costume": "WARDROBE",
            "period": "WARDROBE",
            "uniform": "WARDROBE",
            "vest": "WARDROBE",
            "stunt": "STUNT",
            "water": "ENV_WATER",
            "snow": "ENV_WEATHER",
        }
        low = body.lower()
        for k, v in keywords.items():
            if k in low:
                found.append(f"{v}: {k}")
        return found

    @staticmethod
    def _extract_environmental(body: str) -> List[str]:
        env: List[str] = []
        if re.search(r"\bnight\b", body, flags=re.IGNORECASE):
            env.append("Night")
        if re.search(r"\brain\b|\bfog\b|\bsnow\b|\bstorm\b", body, flags=re.IGNORECASE):
            env.append("Weather: explicit")
        if re.search(r"\bwater\b|\bocean\b|\briver\b|\blake\b", body, flags=re.IGNORECASE):
            env.append("Water: on-location")
        return env

    @staticmethod
    def _extract_dependencies(
        body: str,
        characters: List[str],
        scene_number: int = 1,
        time_of_day: str = "",
    ) -> List[ProductionDependency]:
        """Extracts production dependencies from the hazard catalogue.

        Replaces seven bare substring checks with word-anchored hazard rules
        covering aviation, pyrotechnics, firearms, cold, ice, remoteness,
        wildlife, marine, traffic, vehicle stunts, height, heritage, wildfire,
        minors and public access. Every dependency records the screenplay
        phrases that produced it, so an extraction can be audited against the
        page rather than taken on trust.
        """
        from server.services.hazard_rules import detect_context, detect_hazards

        cast_blob = " ".join(characters or [])
        text = body + "\n" + cast_blob

        context = detect_context(text, time_of_day)
        context_flags = sorted([k for k, v in context.items() if v])

        deps: List[ProductionDependency] = []
        for rule, phrases in detect_hazards(text):
            deps.append(
                ProductionDependency(
                    element=rule.element,
                    category=rule.category,
                    initial_risk=rule.baseline_risk,
                    risk_description=rule.description,
                    requires_external_research=True,
                    research_objective=rule.research_objective,
                    hazard_class=rule.hazard_class,
                    trigger_phrases=phrases[:6],
                    scene_numbers=[scene_number],
                    context_flags=context_flags,
                    query_templates=list(rule.query_templates),
                    blocker_terms=list(rule.blocker_terms),
                    mitigation_template=rule.mitigation_template or None,
                    context_query_templates=[
                        template for flag, template in rule.context_templates
                        if flag in context_flags
                    ],
                )
            )

        if not deps:
            # A scene shot inside a permitted stage is not public-location
            # filming, and telling a producer to obtain a municipal permit the
            # lot's standing permit already covers is simply wrong. Only the
            # displayed reasoning changes here: the element, category, research
            # objective and queries are identical either way, so evidence
            # binding and the score are unaffected.
            controlled_stage = ScriptParser._is_controlled_stage(body, time_of_day)

            if controlled_stage:
                description = (
                    "Interior work on a permitted studio stage relies on the lot's standing "
                    "permit and controlled access rather than a public-location film permit."
                )
                mitigation = (
                    "Confirm the stage booking sits under the lot's standing permit, and that "
                    "stage access, load-in and fire-lane conditions are agreed with the lot."
                )
            else:
                description = (
                    "Public location filming typically requires municipal film office permits "
                    "and notifications."
                )
                mitigation = None

            deps.append(
                ProductionDependency(
                    element="Location Filming Permit",
                    category=DependencyCategory.LOCATIONS_AND_ACCESS,
                    initial_risk=RiskLevel.YELLOW,
                    risk_description=description,
                    requires_external_research=True,
                    research_objective="Verify municipal film permit rules for the location",
                    hazard_class="LOCATION_PERMIT",
                    trigger_phrases=[],
                    scene_numbers=[scene_number],
                    context_flags=context_flags,
                    query_templates=["municipal film permit requirements {jurisdiction}"],
                    mitigation_template=mitigation,
                )
            )

        return deps

    @staticmethod
    def _is_controlled_stage(body: str, slug_and_time: str) -> bool:
        """True for an interior scene the screenplay places on a permitted stage.

        Requires both an interior setting and an explicit stage/lot statement,
        so an exterior scene that merely mentions a studio is not swept in.
        """
        blob = f"{slug_and_time} {body}".lower()
        interior = bool(re.search(r"\bint\b|\binterior\b", blob))
        stage = bool(re.search(r"\bsound\s?stage\b|\bstudio\s+lot\b|\bbacklot\b", blob))
        permitted = bool(re.search(r"\bpermitted\b|\bstanding\s+permit\b|\bcertified\b", blob))
        return interior and stage and permitted

    @staticmethod
    def _compose_overall_summary(scenes: List[Scene]) -> str:
        if not scenes:
            return "No scenes parsed."
        top = scenes[0]
        return f"Parsed {len(scenes)} scene(s). Lead scene: {top.summary}"
"""Screenplay Ingestion and Normalization Service.

Supports:
- Pasted / plain-text screenplays (industry standard format)
- Fountain screenplay format (.fountain)
- PDF uploads using pure-Python text extraction or Gemini multimodal Part preparation
- Deterministic extraction of scenes, sluglines, cast, props, SFX, and dependencies
- Direct normalization into ScreenplayBreakdown Pydantic models
"""

import re
from typing import Any, List, Optional, Tuple, Union
import zlib
from google.genai import types

from server.models.screenplay import (
    Character,
    DependencyCategory,
    EnvironmentalFactor,
    PhysicalElement,
    ProductionDependency,
    RiskLevel,
    Scene,
    ScreenplayBreakdown,
    SettingType,
    Slugline,
    TimeOfDay,
)

# Common transitions to ignore as character cues
_TRANSITIONS = {
    "CUT TO:", "FADE IN:", "FADE OUT.", "DISSOLVE TO:", "SMASH CUT TO:",
    "JUMP CUT TO:", "MATCH CUT TO:", "BACK TO:", "FLASHBACK:", "END FLASHBACK.",
}

# Regex for standard and Fountain sluglines
_SLUGLINE_RE = re.compile(
    r"^(?:(?:\.|\b)(INT\.|EXT\.|INT/EXT\.|EXT/INT\.|I/E\.|EST\.)\s+([^-—\n\r]+)(?:[-—]\s*(.+))?)$",
    re.IGNORECASE,
)

# Fountain forced slugline (starts with single dot followed by uppercase/alphanumeric)
_FOUNTAIN_FORCED_SLUGLINE_RE = re.compile(
    r"^\.([A-Z0-9][^\n\r]+)$"
)

# Character cue regex: uppercase string on a line by itself
_CHARACTER_CUE_RE = re.compile(
    r"^(?:@)?([A-Z][A-Z0-9\s\.\-']{1,28})(?:\s*\(.*\))?$"
)


def is_fountain_format(text: str) -> bool:
    """Heuristic check to detect if text contains Fountain screenplay markup."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    # Check for title page metadata (Title:, Author:, Credit:)
    has_title_page = any(lines[i].lower().startswith(("title:", "author:", "credit:", "draft date:")) for i in range(min(5, len(lines))))
    # Check for forced scene headings or transitions
    has_forced_scenes = any(_FOUNTAIN_FORCED_SLUGLINE_RE.match(l) for l in lines)
    has_scene_headings = any(_SLUGLINE_RE.match(l) for l in lines)
    return has_title_page or has_forced_scenes or (has_scene_headings and len(lines) > 2)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts raw text streams from standard text-based PDF bytes without 3rd party dependencies.

    Returns extracted text if decodable, or an empty string if scanned or encrypted.
    """
    if not pdf_bytes.startswith(b"%PDF"):
        return ""

    extracted_chunks: List[str] = []
    # Scan for compressed streams (FlateDecode)
    stream_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
    text_token_pattern = re.compile(r"\((.*?)\)\s*Tj", re.DOTALL)
    bracket_token_pattern = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)

    for match in stream_pattern.finditer(pdf_bytes):
        raw_stream = match.group(1)
        decompressed: Optional[bytes] = None
        try:
            decompressed = zlib.decompress(raw_stream)
        except Exception:
            try:
                # Raw deflate with negative wbits
                decompressed = zlib.decompress(raw_stream, -zlib.MAX_WBITS)
            except Exception:
                pass

        if decompressed:
            try:
                stream_text = decompressed.decode("latin-1", errors="ignore")
                # Extract text inside (text) Tj operators
                for tj_match in text_token_pattern.finditer(stream_text):
                    cleaned = tj_match.group(1).replace(r"\(", "(").replace(r"\)", ")")
                    if cleaned.strip():
                        extracted_chunks.append(cleaned)
                # Extract text inside [(t)(e)(x)(t)] TJ operators
                for tj_bracket in bracket_token_pattern.finditer(stream_text):
                    bracket_content = tj_bracket.group(1)
                    inner_texts = re.findall(r"\((.*?)\)", bracket_content)
                    if inner_texts:
                        extracted_chunks.append("".join(inner_texts))
            except Exception:
                continue

    return "\n".join(extracted_chunks).strip()


def prepare_gemini_multimodal_part(content_bytes: bytes, mime_type: str = "application/pdf") -> types.Part:
    """Prepares raw PDF bytes for direct Gemini native multimodal document understanding."""
    return types.Part.from_bytes(data=content_bytes, mime_type=mime_type)


def parse_slugline(line: str) -> Slugline:
    """Parses a scene header into a structured Slugline model."""
    raw = line.strip().lstrip(".")
    upper = raw.upper()

    setting = SettingType.UNKNOWN
    if "INT/EXT" in upper or "EXT/INT" in upper or "I/E" in upper:
        setting = SettingType.INT_EXT
    elif "INT." in upper or upper.startswith("INT "):
        setting = SettingType.INT
    elif "EXT." in upper or upper.startswith("EXT "):
        setting = SettingType.EXT

    location = "UNSPECIFIED LOCATION"
    time_of_day = TimeOfDay.UNSPECIFIED

    # Split by hyphen or dash if present
    separator = " - " if " - " in raw else ("-" if "-" in raw else None)
    if separator:
        parts = raw.split(separator, 1)
        loc_candidate = parts[0]
        # Clean prefix
        loc_candidate = re.sub(r"^(?:INT\.|EXT\.|INT/EXT\.|EXT/INT\.|I/E\.|EST\.)\s*", "", loc_candidate, flags=re.IGNORECASE).strip()
        if loc_candidate:
            location = loc_candidate

        time_part = parts[1].strip().upper()
        if "NIGHT" in time_part:
            time_of_day = TimeOfDay.NIGHT
        elif "DAY" in time_part:
            time_of_day = TimeOfDay.DAY
        elif "DAWN" in time_part:
            time_of_day = TimeOfDay.DAWN
        elif "DUSK" in time_part:
            time_of_day = TimeOfDay.DUSK
        elif "MAGIC" in time_part:
            time_of_day = TimeOfDay.MAGIC_HOUR
        elif "CONTINUOUS" in time_part:
            time_of_day = TimeOfDay.CONTINUOUS
    else:
        # Fallback if no hyphen separator
        cleaned = re.sub(r"^(?:INT\.|EXT\.|INT/EXT\.|EXT/INT\.|I/E\.|EST\.)\s*", "", raw, flags=re.IGNORECASE).strip()
        if cleaned:
            location = cleaned

    return Slugline(
        raw=line.strip(),
        setting=setting,
        location=location,
        time_of_day=time_of_day,
    )


def _detect_deterministic_dependencies(text: str, location: str) -> List[ProductionDependency]:
    """Deterministically extracts production dependencies based on screenplay keywords."""
    deps: List[ProductionDependency] = []
    text_lower = text.lower()

    # 1. Aviation / Drone
    if any(k in text_lower for k in ["drone", "uav", "fpv", "quadcopter", "airspace"]):
        deps.append(
            ProductionDependency(
                element="Low-Altitude Drone / UAV Operations",
                category=DependencyCategory.PERMITS_AND_LEGAL,
                initial_risk=RiskLevel.RED,
                risk_description="Night aerial drone operations over public structures or active traffic require FAA Part 107 waivers and municipal agency authorization.",
                requires_external_research=True,
                research_objective=f"Verify FAA Part 107 drone waiver rules and local filming permits for {location}",
            )
        )

    # 2. Pyrotechnics / Fire / Explosives
    if any(k in text_lower for k in ["explosion", "fireball", "pyrotechnic", "blast", "detonate", "flame", "dynamite"]):
        deps.append(
            ProductionDependency(
                element="Pyrotechnics & Open-Flame Effects",
                category=DependencyCategory.SAFETY_AND_STUNTS,
                initial_risk=RiskLevel.RED,
                risk_description="Live explosive practical effects and open flame require licensed pyrotechnic operators, fire marshal permits, and dedicated standby fire apparatus.",
                requires_external_research=True,
                research_objective=f"Verify municipal fire marshal pyrotechnic permitting guidelines and safety buffers for {location}",
            )
        )

    # 3. Open Water / Marine Safety
    if any(k in text_lower for k in ["bridge", "river", "ocean", "harbor", "open water", "fjord", "sea ice"]):
        deps.append(
            ProductionDependency(
                element="Waterborne & Marine Stunt Filming",
                category=DependencyCategory.SAFETY_AND_STUNTS,
                initial_risk=RiskLevel.YELLOW,
                risk_description="Filming above or upon navigable waters requires Coast Guard notifications, marine safety rescue craft, and water rescue personnel.",
                requires_external_research=True,
                research_objective=f"Verify marine safety vessel mandates and waterway authority filming restrictions for {location}",
            )
        )

    # 4. Extreme Cold / Arctic Logistics
    if any(k in text_lower for k in ["glacier", "arctic", "-30", "-32", "blizzard", "sub-zero", "polar bear", "crevasse"]):
        deps.append(
            ProductionDependency(
                element="Sub-Zero Arctic Operations & Wildlife Protection",
                category=DependencyCategory.WEATHER_AND_ENVIRONMENT,
                initial_risk=RiskLevel.YELLOW,
                risk_description="Extreme sub-zero operations mandate specialized thermal camera gear, polar wildlife defense safety protocols, and emergency medical evacuation plans.",
                requires_external_research=True,
                research_objective=f"Verify environmental field regulations and safety requirements for {location}",
            )
        )

    # 5. Weapons / Gunfire Simulation
    if any(k in text_lower for k in ["gunfire", "rifle", "shotgun", "pistol", "revolver", "submachine", "weapon"]):
        deps.append(
            ProductionDependency(
                element="Simulated Weapons & Blank Gunfire",
                category=DependencyCategory.SAFETY_AND_STUNTS,
                initial_risk=RiskLevel.YELLOW,
                risk_description="Discharging prop firearms in exterior public spaces requires certified on-set armorer oversight and local law enforcement notification.",
                requires_external_research=True,
                research_objective=f"Verify police department notification requirements for blank gunfire filming in {location}",
            )
        )

    return deps


def _detect_physical_elements(text: str) -> List[str]:
    """Identifies physical props, picture vehicles, and equipment mentioned in action lines."""
    elements: List[str] = []
    text_lower = text.lower()
    mapping = [
        (["drone", "quadcopter", "fpv"], "FPV Tactical Drone"),
        (["snowmobile", "twin-track"], "Twin-Track Arctic Snowmobile"),
        (["van", "delivery van", "truck", "armored transport"], "Picture Vehicle / Transport"),
        (["rifle", "flare rifle", "pistol", "gun", "firearm"], "Prop Weaponry / Armory"),
        (["parka", "survival gear", "headset", "telemetry"], "Specialized Wardrobe / Headset"),
        (["gas lamp", "gantry", "cables", "iron fence"], "Location Set Dressing / Rigging"),
    ]
    for keywords, label in mapping:
        if any(k in text_lower for k in keywords):
            elements.append(label)
    return elements


def _detect_stunts_and_sfx(text: str) -> List[str]:
    """Identifies physical stunts and practical special effects."""
    sfx: List[str] = []
    text_lower = text.lower()
    if any(k in text_lower for k in ["explosion", "fireball", "blast", "showering embers"]):
        sfx.append("Practical Pyrotechnic Explosion")
    if any(k in text_lower for k in ["dives vertically", "skimming inches", "high-speed", "maneuvers", "fractures"]):
        sfx.append("High-Speed Precision Vehicle Maneuvers")
    if any(k in text_lower for k in ["gunfire echoes", "discharging", "shoots", "blast plan"]):
        sfx.append("Simulated Gunfire / Practical Muzzle Discharge")
    return sfx


def _detect_environmental_factors(text: str, time_of_day: TimeOfDay) -> List[str]:
    """Identifies lighting, weather, and atmospheric scene constraints."""
    factors: List[str] = []
    if time_of_day == TimeOfDay.NIGHT:
        factors.append("Night Exterior Lighting")
    text_lower = text.lower()
    if "rain" in text_lower:
        factors.append("Wet Surface / Rain Machine")
    if any(k in text_lower for k in ["blizzard", "snow", "whiteout"]):
        factors.append("Arctic Blizzard / Whiteout Conditions")
    if any(k in text_lower for k in ["wind", "knots", "gale"]):
        factors.append("High Wind Conditions")
    if any(k in text_lower for k in ["sub-zero", "-30", "-32", "freezing"]):
        factors.append("Sub-Zero Extreme Temperature (-30°C)")
    return factors


def parse_text_screenplay(
    text: str,
    title: Optional[str] = None,
) -> ScreenplayBreakdown:
    """Parses plain-text or Fountain screenplay into a structured ScreenplayBreakdown model.

    Preserves scene boundaries, characters, physical elements, actions, SFX, and dependencies.
    """
    if not text or not text.strip():
        raise ValueError("Screenplay content is empty or contains only whitespace.")

    lines = [line.rstrip() for line in text.splitlines()]
    derived_title = title or "Screenplay Project"
    author_name = "Production Intelligence Ingestion"

    # Extract title and author from Fountain title page if present
    for idx in range(min(15, len(lines))):
        lowered = lines[idx].lower().strip()
        if lowered.startswith("title:"):
            derived_title = lines[idx].split(":", 1)[1].strip()
        elif lowered.startswith("author:") or lowered.startswith("authors:"):
            author_name = lines[idx].split(":", 1)[1].strip()

    # Segment lines into scenes based on slugline detection
    scene_blocks: List[Tuple[str, List[str]]] = []
    current_slugline: Optional[str] = None
    current_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        is_slugline = bool(_SLUGLINE_RE.match(stripped) or _FOUNTAIN_FORCED_SLUGLINE_RE.match(stripped))

        if is_slugline:
            if current_slugline:
                # Save preceding scene block
                scene_blocks.append((current_slugline, current_lines))
                current_lines = []
            else:
                # Lines prior to first slugline are preamble/title page metadata - discard
                current_lines = []
            current_slugline = stripped
        else:
            if stripped:
                # Ignore title page lines before any slugline
                if not current_slugline and stripped.lower().startswith(
                    ("title:", "author:", "credit:", "draft date:", "source:", "notes:", "copyright:")
                ):
                    continue
                current_lines.append(stripped)

    # Append trailing scene block
    if current_slugline:
        scene_blocks.append((current_slugline, current_lines))
    elif current_lines:
        # Script had NO sluglines whatsoever; wrap all lines into single fallback scene
        scene_blocks.append(("EXT. GENERAL LOCATION - DAY", current_lines))

    # If no scenes were recognized (e.g. malformed or single description), create fallback scene
    if not scene_blocks:
        scene_blocks = [("EXT. GENERAL LOCATION - DAY", current_lines)]

    parsed_scenes: List[Scene] = []

    for scene_idx, (slug_str, scene_content_lines) in enumerate(scene_blocks, start=1):
        slugline_obj = parse_slugline(slug_str)
        scene_body = "\n".join(scene_content_lines)

        # Detect characters
        characters: List[str] = []
        for line in scene_content_lines:
            line_str = line.strip()
            # Ignore scene headers or transitions
            if _SLUGLINE_RE.match(line_str) or line_str in _TRANSITIONS:
                continue
            char_match = _CHARACTER_CUE_RE.match(line_str)
            if char_match:
                name = char_match.group(1).strip()
                # Skip if common transition or single character artifact
                if name not in _TRANSITIONS and len(name) >= 2 and not name.startswith(("INT", "EXT")):
                    if name not in characters:
                        characters.append(name)

        # Extract elements and dependencies
        props = _detect_physical_elements(scene_body)
        sfx = _detect_stunts_and_sfx(scene_body)
        environment = _detect_environmental_factors(scene_body, slugline_obj.time_of_day)
        dependencies = _detect_deterministic_dependencies(scene_body, slugline_obj.location)

        # Estimate page count (standard screenplay: ~55 lines per page, minimum 0.25 page)
        line_count = len(scene_content_lines)
        page_estimate = round(max(0.25, line_count / 55.0), 2)

        # Build concise scene summary
        summary = (
            scene_content_lines[0]
            if scene_content_lines
            else f"Scene taking place at {slugline_obj.location}."
        )
        if len(summary) > 140:
            summary = summary[:137] + "..."

        parsed_scenes.append(
            Scene(
                scene_number=scene_idx,
                slugline=slugline_obj,
                summary=summary,
                page_count=page_estimate,
                characters=characters,
                props_and_wardrobe=props,
                stunts_and_sfx=sfx,
                environmental_factors=environment,
                dependencies=dependencies,
            )
        )

    return ScreenplayBreakdown(
        project_title=derived_title,
        author=author_name,
        screenplay_summary=f"Automated breakdown of {len(parsed_scenes)} scene(s) extracted from script source.",
        total_scenes=len(parsed_scenes),
        scenes=parsed_scenes,
    )


def parse_screenplay(
    content: Union[str, bytes],
    filename: Optional[str] = None,
    title: Optional[str] = None,
) -> ScreenplayBreakdown:
    """Master ingestion entrypoint for all screenplay formats.

    Args:
        content: Plain-text string, Fountain string, or raw PDF bytes.
        filename: Optional filename to assist format detection (.fountain, .pdf, .txt).
        title: Optional project title override.

    Returns:
        Structured ScreenplayBreakdown model populated with extracted entities.
    """
    if isinstance(content, bytes):
        # 1. Handle PDF binary
        if content.startswith(b"%PDF"):
            extracted_text = extract_text_from_pdf(content)
            if extracted_text and len(extracted_text.strip()) >= 30:
                doc_title = title or (filename.rsplit(".", 1)[0] if filename else "PDF Screenplay")
                return parse_text_screenplay(extracted_text, title=doc_title)
            else:
                # Fallback: create high-level PDF placeholder ready for Gemini native multimodal parsing
                doc_title = title or (filename.rsplit(".", 1)[0] if filename else "Multimodal Screenplay")
                default_slug = Slugline(
                    raw="EXT. MULTIMODAL PDF SEQUENCE - DAY",
                    setting=SettingType.EXT,
                    location="MULTIMODAL PDF SEQUENCE",
                    time_of_day=TimeOfDay.DAY,
                )
                return ScreenplayBreakdown(
                    project_title=doc_title,
                    author="Gemini Native Multimodal PDF",
                    screenplay_summary="Screenplay ingested from PDF bytes. Ready for Gemini multimodal document intelligence.",
                    total_scenes=1,
                    scenes=[
                        Scene(
                            scene_number=1,
                            slugline=default_slug,
                            summary="Ingested PDF document requiring Gemini native document understanding.",
                            page_count=1.0,
                            characters=[],
                            dependencies=[
                                ProductionDependency(
                                    element="Multimodal PDF Ingestion",
                                    category=DependencyCategory.LOCATIONS_AND_ACCESS,
                                    initial_risk=RiskLevel.YELLOW,
                                    risk_description="Extracted from raw PDF document stream.",
                                    requires_external_research=False,
                                )
                            ],
                        )
                    ],
                )
        else:
            # Attempt decoding bytes as UTF-8 text
            text_str = content.decode("utf-8", errors="replace")
            return parse_text_screenplay(text_str, title=title)

    # 2. Handle string content (Fountain or plain text)
    return parse_text_screenplay(content, title=title)
