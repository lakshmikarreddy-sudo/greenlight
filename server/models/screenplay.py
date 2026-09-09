"""Screenplay domain models for production intelligence extraction."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SettingType(str, Enum):
    """Interior vs Exterior scene setting."""
    INT = "INT"
    EXT = "EXT"
    INT_EXT = "INT/EXT"
    UNKNOWN = "UNKNOWN"


class TimeOfDay(str, Enum):
    """Time of day specification from screenplay slugline."""
    DAY = "DAY"
    NIGHT = "NIGHT"
    DAWN = "DAWN"
    DUSK = "DUSK"
    MAGIC_HOUR = "MAGIC HOUR"
    CONTINUOUS = "CONTINUOUS"
    UNSPECIFIED = "UNSPECIFIED"


class DependencyCategory(str, Enum):
    """Production dependency category for film logistics."""
    PERMITS_AND_LEGAL = "PERMITS_AND_LEGAL"
    SAFETY_AND_STUNTS = "SAFETY_AND_STUNTS"
    WEATHER_AND_ENVIRONMENT = "WEATHER_AND_ENVIRONMENT"
    EQUIPMENT_AND_GEAR = "EQUIPMENT_AND_GEAR"
    LOCATIONS_AND_ACCESS = "LOCATIONS_AND_ACCESS"
    CAST_AND_LABOR = "CAST_AND_LABOR"


class RiskLevel(str, Enum):
    """Three-tier risk rating for production elements."""
    GREEN = "GREEN"      # Low concern / routine protocol
    YELLOW = "YELLOW"    # Review required / conditional friction
    RED = "RED"          # Critical production risk / schedule blocker


class Slugline(BaseModel):
    """Structured scene heading information."""
    raw: str = Field(..., description="Full raw slugline as written in script, e.g. EXT. BROOKLYN BRIDGE - NIGHT")
    setting: SettingType = Field(default=SettingType.UNKNOWN, description="Interior, Exterior, or hybrid")
    location: str = Field(..., description="Location name, e.g. BROOKLYN BRIDGE")
    time_of_day: TimeOfDay = Field(default=TimeOfDay.UNSPECIFIED, description="Lighting and time context")


class Character(BaseModel):
    """Character appearing in a scene with production implications."""
    name: str = Field(..., description="Character name in script")
    role_type: str = Field(default="SPEAKING", description="PRINCIPAL, SPEAKING, STUNT_DOUBLE, BACKGROUND_EXTRA, or CHILD_ACTOR")
    description: Optional[str] = Field(default=None, description="Brief context or wardrobe/look description")
    is_minor: bool = Field(default=False, description="Whether the actor is a minor (triggers child labor laws)")
    special_notes: Optional[str] = Field(default=None, description="Union, stunt, or specialized handling notes")


class PhysicalElement(BaseModel):
    """Physical asset required on set (props, vehicles, wardrobe, practical SFX)."""
    name: str = Field(..., description="Name of the physical element")
    category: str = Field(..., description="PROP, VEHICLE, WARDROBE, WEAPON, SFX_PRACTICAL, or MAKEUP")
    description: Optional[str] = Field(default=None, description="Specific details or handling requirements")
    is_hazardous: bool = Field(default=False, description="Involves weapons, fire, pyrotechnics, or high speed")


class EnvironmentalFactor(BaseModel):
    """Atmospheric or natural condition mandated by the scene."""
    condition_type: str = Field(..., description="WEATHER, LIGHTING, WATER, TEMPERATURE, or ALTITUDE")
    description: str = Field(..., description="Description of condition, e.g. 'Heavy winter snowfall at sea level'")
    requires_practical_effects: bool = Field(default=False, description="True if artificially created on set")


class ProductionDependency(BaseModel):
    """An individual production constraint or entity requiring logistical planning."""
    element: str = Field(..., description="Short name of the constrained element")
    category: DependencyCategory = Field(..., description="Domain category of the dependency")
    initial_risk: RiskLevel = Field(default=RiskLevel.YELLOW, description="Preliminary assessment before deep research")
    risk_description: str = Field(..., description="Why this dependency presents production or schedule friction")
    requires_external_research: bool = Field(default=True, description="True if real-world verification is needed")
    research_objective: Optional[str] = Field(default=None, description="Formulated objective for external search")

    # --- Extraction provenance and production context (C1/C2) -------------
    hazard_class: Optional[str] = Field(default=None, description="Standard hazard class this dependency belongs to")
    trigger_phrases: List[str] = Field(default_factory=list, description="Exact screenplay phrases that produced this dependency")
    scene_numbers: List[int] = Field(default_factory=list, description="Scenes in which this hazard appears")
    context_flags: List[str] = Field(default_factory=list, description="Scene facts that aggravate the hazard, e.g. night_work")
    query_templates: List[str] = Field(default_factory=list, description="Jurisdiction-qualified research query templates")
    blocker_terms: List[str] = Field(default_factory=list, description="Vocabulary indicating this specific activity is legally barred")
    context_query_templates: List[str] = Field(default_factory=list, description="Extra queries raised because of this scene's context")
    mitigation_template: Optional[str] = Field(default=None, description="Hazard-specific mitigation guidance for a producer")


class Scene(BaseModel):
    """Structured breakdown of an individual screenplay scene."""
    scene_number: int = Field(..., description="Sequential scene index")
    context_flags: List[str] = Field(default_factory=list, description="Scene-level production facts, e.g. night_work, public_access")
    slugline: Slugline = Field(..., description="Parsed scene heading")
    summary: str = Field(..., description="Concise synopsis of the action and dramatic intent")
    page_count: Optional[float] = Field(default=None, description="Estimated page length (e.g. 1.5 pages)")
    characters: List[str] = Field(default_factory=list, description="Names of characters present")
    props_and_wardrobe: List[str] = Field(default_factory=list, description="Key props, wardrobe items, and vehicles")
    stunts_and_sfx: List[str] = Field(default_factory=list, description="Stunts, pyrotechnics, practical effects")
    environmental_factors: List[str] = Field(default_factory=list, description="Weather and lighting requirements")
    dependencies: List[ProductionDependency] = Field(default_factory=list, description="Extracted logistical dependencies")


class ScreenplayBreakdown(BaseModel):
    """Complete structured breakdown of an ingested screenplay or scene sequence."""
    project_title: str = Field(..., description="Title of the project or screenplay")
    author: Optional[str] = Field(default=None, description="Screenplay author or source")
    screenplay_summary: str = Field(..., description="Executive narrative summary of the script")
    total_scenes: int = Field(..., description="Count of scenes analyzed")
    scenes: List[Scene] = Field(default_factory=list, description="List of parsed scenes")
    jurisdiction_label: Optional[str] = Field(default=None, description="Resolved filming jurisdiction, e.g. 'Savannah, Georgia, United States'")
