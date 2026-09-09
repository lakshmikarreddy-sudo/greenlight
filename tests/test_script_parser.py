"""Tests for deterministic ScriptParser service (Stage 4)."""
import pytest

from server.services.script_parser import ScriptParser, ParseError, PDFRequiresGeminiError
from server.models.screenplay import ScreenplayBreakdown, ProductionDependency


def test_plain_text_parsing_basic():
    txt = """
INT. BROOKLYN BRIDGE - NIGHT
AGENT VANCE
(breathing hard)
He runs across the span as the drone whirs overhead.
PILOT
We have a visual.
"""
    result = ScriptParser.parse_text(txt, project_title="Test Project")
    assert isinstance(result, ScreenplayBreakdown)
    assert result.total_scenes >= 1
    # character extraction deterministic
    names = result.scenes[0].characters
    assert "AGENT VANCE" in names
    assert "PILOT" in names
    # dependency extraction recognizes drone
    deps = result.scenes[0].dependencies
    assert any("Drone" in d.element or "Drone" in str(d.element) or "drone" in d.element.lower() for d in deps)


def test_fountain_parsing():
    fountain = ".INT. WAREHOUSE - DAY\nMANN\nHe lights the cigarette.\n"
    res = ScriptParser.parse_fountain(fountain, project_title="Fountain Test")
    assert isinstance(res, ScreenplayBreakdown)
    assert res.total_scenes == 1
    assert any(c for c in res.scenes[0].characters if "MANN" in c)


def test_empty_input_raises():
    with pytest.raises(ParseError):
        ScriptParser.parse_text("")


def test_malformed_input_handling():
    # malformed here is None
    with pytest.raises(ParseError):
        ScriptParser.parse_text(None)


def test_multiple_scene_boundaries():
    txt = """
EXT. PARK - DAY
MAN
He sits on a bench.

INT. APARTMENT - NIGHT
WOMAN
She answers the phone.
"""
    res = ScriptParser.parse_text(txt)
    assert res.total_scenes == 2
    locs = [s.slugline.location for s in res.scenes]
    assert any("PARK" in l.upper() or "PARK" == l.upper() for l in locs)
    assert any("APARTMENT" in l.upper() or "APARTMENT" == l.upper() for l in locs)


def test_character_extraction_deterministic():
    txt = """
INT. ROOM - DAY
BOB
Hello.
BOB JR
(whispering)
This is a test.
"""
    res = ScriptParser.parse_text(txt)
    chars = res.scenes[0].characters
    assert "BOB" in chars
    assert "BOB JR" in chars


def test_production_dependency_extraction():
    txt = """
EXT. DOCKS - NIGHT
A boat drifts. An explosion lights the water. A child watches.
"""
    res = ScriptParser.parse_text(txt)
    deps = res.scenes[0].dependencies
    elements = [d.element for d in deps]
    # Should detect pyrotechnic / explosion and water
    assert any("Pyrotechnic" in e or "Pyrotechnic" in str(e) or "explosion" in e.lower() for e in elements)
    assert any("Water" in e or "Water" in str(e) or "water" in e.lower() for e in elements)


def test_pdf_handling_fallback():
    with pytest.raises(PDFRequiresGeminiError):
        ScriptParser.parse_pdf(b"%PDF-1.4 binary data")


def test_pydantic_validation_of_breakdown():
    txt = "INT. ROOM - DAY\nALICE\nHello"
    res = ScriptParser.parse_text(txt, project_title="PD Test")
    # model_dump should succeed
    d = res.model_dump()
    assert d.get("project_title") == "PD Test"
"""Unit tests for Screenplay Ingestion and Normalization service."""

import pytest
import zlib
from google.genai import types

from server.models.screenplay import (
    DependencyCategory,
    RiskLevel,
    ScreenplayBreakdown,
    SettingType,
    TimeOfDay,
)
from server.services.script_parser import (
    extract_text_from_pdf,
    is_fountain_format,
    parse_screenplay,
    parse_slugline,
    parse_text_screenplay,
    prepare_gemini_multimodal_part,
)


# ------------------------------------------------------------------------------
# Test 1: Plain Text Screenplay Ingestion
# ------------------------------------------------------------------------------
def test_plain_text_ingestion():
    """Tests standard plain text screenplay parsing with multiple scenes, sluglines, and cast."""
    script = """EXT. BROOKLYN BRIDGE - NIGHT

Rain slicks the pavement. A tactical drone hovers above the suspension cables.

AGENT VANCE
(into radio)
Target is approaching the lower span.

INT. SURVEILLANCE VAN - CONTINUOUS

TECH OPERATOR
Visual confirmed. Deploying the tracker."""

    breakdown = parse_screenplay(script, title="Bridge Operation")

    assert isinstance(breakdown, ScreenplayBreakdown)
    assert breakdown.project_title == "Bridge Operation"
    assert breakdown.total_scenes == 2

    # Verify Scene 1
    scene1 = breakdown.scenes[0]
    assert scene1.scene_number == 1
    assert scene1.slugline.setting == SettingType.EXT
    assert "BROOKLYN" in scene1.slugline.location.upper()
    assert scene1.slugline.time_of_day == TimeOfDay.NIGHT
    assert "AGENT VANCE" in scene1.characters
    assert len(scene1.dependencies) > 0

    # Verify Scene 2
    scene2 = breakdown.scenes[1]
    assert scene2.scene_number == 2
    assert scene2.slugline.setting == SettingType.INT
    assert "VAN" in scene2.slugline.location.upper()
    assert scene2.slugline.time_of_day == TimeOfDay.CONTINUOUS
    assert "TECH OPERATOR" in scene2.characters


# ------------------------------------------------------------------------------
# Test 2: Fountain Format Screenplay Ingestion
# ------------------------------------------------------------------------------
def test_fountain_format_ingestion():
    """Tests Fountain format detection, title page extraction, and forced scene headings."""
    fountain_script = """Title: The Arctic Gambit
Author: Cinema Scribe
Draft date: 2026-09-04

.ROOFTOP HELIPAD - DAWN

The twin turbines whine into life as cold mist rolls across the deck.

CAPTAIN MILLER
All teams, spin up. We have fifteen minutes to clearance.

CUT TO:

EXT. FJORD CROSSING - DAY

A rescue cutter cuts through loose fjord ice."""

    assert is_fountain_format(fountain_script) is True

    breakdown = parse_screenplay(fountain_script)
    assert breakdown.project_title == "The Arctic Gambit"
    assert breakdown.total_scenes == 2

    scene1 = breakdown.scenes[0]
    assert "HELIPAD" in scene1.slugline.location.upper()
    assert scene1.slugline.time_of_day == TimeOfDay.DAWN
    assert "CAPTAIN MILLER" in scene1.characters
    assert "CUT TO:" not in scene1.characters


# ------------------------------------------------------------------------------
# Test 3: Empty and Malformed Input Handling
# ------------------------------------------------------------------------------
def test_empty_input_raises_value_error():
    """Verifies that empty string or whitespace-only raises ValueError."""
    with pytest.raises(ValueError, match="empty or contains only whitespace"):
        parse_screenplay("")

    with pytest.raises(ValueError, match="empty or contains only whitespace"):
        parse_screenplay("   \n\n\t  ")


def test_malformed_script_without_sluglines():
    """Verifies that text without standard sluglines is safely wrapped into a default Scene 1."""
    text = "Marcus walks down an alleyway looking for the contact. No scene header was written."
    breakdown = parse_screenplay(text, title="Unformatted Scene")

    assert isinstance(breakdown, ScreenplayBreakdown)
    assert breakdown.total_scenes == 1
    assert breakdown.scenes[0].scene_number == 1
    assert breakdown.scenes[0].slugline.setting in (SettingType.EXT, SettingType.UNKNOWN)


# ------------------------------------------------------------------------------
# Test 4: Scene Boundary Detection
# ------------------------------------------------------------------------------
def test_scene_boundary_detection():
    """Verifies sequential scene numbering and clear scene boundary preservation."""
    script = """INT. SAFE HOUSE - DAY
Marcus checks his ammunition.

EXT. HARBOR DOCKS - NIGHT
The freighter docks silently in the fog.

INT. FREIGHTER HOLD - NIGHT
Containers are stacked three stories high."""

    breakdown = parse_screenplay(script)
    assert breakdown.total_scenes == 3
    numbers = [s.scene_number for s in breakdown.scenes]
    assert numbers == [1, 2, 3]
    settings_list = [s.slugline.setting for s in breakdown.scenes]
    assert settings_list == [SettingType.INT, SettingType.EXT, SettingType.INT]


# ------------------------------------------------------------------------------
# Test 5: Character Extraction & Transition Filtering
# ------------------------------------------------------------------------------
def test_character_extraction():
    """Verifies character cues are identified while editing transitions are rejected."""
    script = """EXT. ROOFTOP - NIGHT

SARAH
Do you see the package?

DAVID
(checking binoculars)
Negative, target is obstructed.

DISSOLVE TO:

INT. COMMAND TENT - NIGHT

COLONEL REID
Hold your fire!"""

    breakdown = parse_screenplay(script)
    scene1 = breakdown.scenes[0]
    assert "SARAH" in scene1.characters
    assert "DAVID" in scene1.characters
    assert "DISSOLVE TO:" not in scene1.characters

    scene2 = breakdown.scenes[1]
    assert "COLONEL REID" in scene2.characters


# ------------------------------------------------------------------------------
# Test 6: Deterministic Production Dependency Extraction
# ------------------------------------------------------------------------------
def test_deterministic_dependency_extraction():
    """Verifies that high-risk production elements trigger specific Dependency categories."""
    script = """EXT. MONTEREY SQUARE - NIGHT
A high-speed tactical drone tracks an armored van as a pyrotechnic fireball blast detonates.
Gunfire echoes through the cobblestone square."""

    breakdown = parse_screenplay(script)
    scene = breakdown.scenes[0]
    categories = [d.category for d in scene.dependencies]

    # Drone triggers PERMITS_AND_LEGAL
    assert DependencyCategory.PERMITS_AND_LEGAL in categories
    # Pyrotechnics triggers SAFETY_AND_STUNTS
    assert DependencyCategory.SAFETY_AND_STUNTS in categories

    # Verify at least one RED initial risk was assigned
    risks = [d.initial_risk for d in scene.dependencies]
    assert RiskLevel.RED in risks


# ------------------------------------------------------------------------------
# Test 7: PDF Handling & Fallback Behavior
# ------------------------------------------------------------------------------
def test_synthetic_pdf_text_extraction():
    """Creates a minimal valid PDF stream and tests pure-python text extraction."""
    # Minimal PDF stream with FlateDecode compressed text
    text_content = "(EXT. CITY STREET - DAY) Tj"
    compressed_stream = zlib.compress(text_content.encode("latin-1"))

    synthetic_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Length " + str(len(compressed_stream)).encode() + b" >>\n"
        b"stream\n" + compressed_stream + b"\nendstream\n"
        b"endobj\nxref\ntrailer << /Root 1 0 R >>\n%%EOF"
    )

    extracted = extract_text_from_pdf(synthetic_pdf)
    assert "EXT. CITY STREET - DAY" in extracted


def test_pdf_multimodal_part_preparation():
    """Verifies that PDF bytes are properly prepared as a Gemini multimodal Part."""
    raw_bytes = b"%PDF-1.4 Mock Screenplay Content"
    part = prepare_gemini_multimodal_part(raw_bytes, mime_type="application/pdf")

    assert isinstance(part, types.Part)
    assert part.inline_data.mime_type == "application/pdf"
    assert part.inline_data.data == raw_bytes


def test_pdf_fallback_ingestion_on_scanned_document():
    """Verifies that non-decodable raw PDF bytes gracefully produce a structured multimodal breakdown."""
    scanned_mock_pdf = b"%PDF-1.4 [Scanned Image Stream without decodable text operators]"
    breakdown = parse_screenplay(scanned_mock_pdf, filename="dune_part_two.pdf")

    assert isinstance(breakdown, ScreenplayBreakdown)
    assert breakdown.total_scenes == 1
    assert "dune_part_two" in breakdown.project_title.lower()
    assert breakdown.scenes[0].dependencies[0].element == "Multimodal PDF Ingestion"


# ------------------------------------------------------------------------------
# Test 8: Pydantic Model Round-Trip Serialization
# ------------------------------------------------------------------------------
def test_breakdown_pydantic_roundtrip():
    """Validates that parsed ScreenplayBreakdown models serialize to JSON and deserialize without loss."""
    script = "EXT. DESERT DUNE - DAY\nA lone scout traverses the sand."
    breakdown = parse_screenplay(script, title="Dune Scout")

    json_str = breakdown.model_dump_json()
    reloaded = ScreenplayBreakdown.model_validate_json(json_str)

    assert reloaded.project_title == "Dune Scout"
    assert len(reloaded.scenes) == 1
    assert reloaded.scenes[0].slugline.location == "DESERT DUNE"
