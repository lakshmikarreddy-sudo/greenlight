"""Curated demo scenarios and research fixtures for Greenlight.

Provides realistic screenplay sequences exercising distinct production risk categories:
1. Brooklyn Drone Chase: Permits, aviation/drone flight, traffic, urban night safety.
2. Svalbard Arctic: Extreme sub-zero weather, polar environmental rules, wildlife protection, remote rescue.
3. Savannah Pyro: Historic preservation, fire marshal pyrotechnics, structural safety, street closures.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from server.models.research import ParallelResultItem, ParallelSearchResponse
from server.models.screenplay import DependencyCategory, RiskLevel


class DemoScenario(BaseModel):
    """Structured screenplay demo scenario for production breakdown."""
    id: str = Field(..., description="Unique scenario slug")
    title: str = Field(..., description="Project / Scene Title")
    logline: str = Field(..., description="One-line dramatic summary")
    script_text: str = Field(..., description="Formatted screenplay scene text")
    target_categories: List[DependencyCategory] = Field(..., description="Risk categories exercised")
    primary_dependency: str = Field(..., description="Core logistical challenge")
    sample_search_objective: str = Field(..., description="Objective for external research")
    sample_search_queries: List[str] = Field(..., description="Recommended search queries")
    fallback_response: ParallelSearchResponse = Field(..., description="Realistic fallback research fixture")


# ------------------------------------------------------------------------------
# 1. Brooklyn Drone Chase (Permits, Drone Law, Traffic, Night Safety)
# ------------------------------------------------------------------------------
_BROOKLYN_SCRIPT = """EXT. BROOKLYN BRIDGE - NIGHT

Rain slicks the suspension cables. Below, eastbound traffic crawls along the lower roadway.

A custom carbon-fiber FPV TACTICAL DRONE hums into frame, hovering 15 feet above the steel girders. It dives vertically under the roadway superstructure, chasing an armored transport vehicle.

AGENT VANCE (30s) stands on a lower maintenance gantry, gripping an encrypted telemetry headset.

VANCE
Target is crossing the Manhattan tower. Drone is in blind pursuit.

The drone weaves between oncoming box trucks at 45 mph, skimming inches above the asphalt before banking sharply over the open water of the East River."""


_STAGE_SCRIPT = """INT. SOUNDSTAGE 7 - PERMITTED STUDIO LOT (LOS ANGELES) - DAY

A dressed apartment interior stands under a lighting grid. The stage floor is
marked, cabled and clear. A first aid station sits beside the craft table.

DR. ALINA REYES (40s) sits across a small table from THEO MARCHETTI (50s),
a script in her hands. Two operators work handheld beside them.

ALINA
You keep saying the trial was a success. The committee reads the same
numbers and calls it a failure.

THEO
Because they are reading the summary. I am reading the patients.

Alina slides a folder across the table. Theo does not open it.

THEO (CONT'D)
If I open that, we stop being colleagues.

ALINA
We stopped being colleagues in March.

They hold the silence. The camera pushes in slowly on the folder between them."""



_LA_STREET_SCRIPT = """EXT. SPRING STREET SIDEWALK (LOS ANGELES) - DAY

A single permitted block. Cones and a taped corner hold the line. A certified
traffic control officer waves a delivery van through the intersection while a
marshal in a hi-vis vest keeps two waiting pedestrians behind the tape.

A six-person crew works from the sidewalk: one camera on sticks, a sound
mixer, a bounce board. No lighting rig, no track, no effects.

MAYA CORDERO (30s) and DEV RAMANATHAN (30s) walk the length of the block,
coffee cups in hand, talking the whole way.

MAYA
You told the board it was finished.

DEV
It is finished. It just isn't good.

MAYA
Those are different sentences, Dev. Only one of them was in the email.

DEV
I know what I wrote.

They stop at the corner. The officer holds the van. The city goes on around
them, patient and ordinary.

MAYA
Then say the other one out loud. Once. To me.

Dev looks at the pavement, then at her, and does not say it."""


_BROOKLYN_FALLBACK = ParallelSearchResponse(
    search_id="par_demo_brooklyn_01",
    results=[
        ParallelResultItem(
            url="https://www.nyc.gov/site/mome/permits/uas-guidelines.page",
            title="NYC Mayor's Office of Media and Entertainment - UAS (Drone) Filming Guidelines",
            publish_date="2024-02-10",
            excerpts=[
                "Filming with Uncrewed Aircraft Systems (UAS) in New York City requires an agency permit issued by MOME in consultation with the NYPD and DOT.",
                "Applications for UAS filming must be submitted at least 30 business days prior to scheduled production, with night flights and bridge operations subject to additional security clearance.",
                "Flights directly over moving vehicular traffic or pedestrians are strictly prohibited under FAA Part 107 unless a specific 107.39 waiver is held.",
            ],
        ),
        ParallelResultItem(
            url="https://www.faa.gov/uas/commercial_operators/part_107_waivers",
            title="FAA Part 107 Waivers for Commercial Operations Over Moving Vehicles",
            publish_date="2024-01-18",
            excerpts=[
                "Operations over moving vehicles require an FAA Certificate of Waiver under 14 CFR § 107.39 and § 107.145.",
                "Standard processing time for FAA waiver applications averages 60 to 90 days. Proof of closed-course traffic controls or propeller containment is required.",
            ],
        ),
    ],
    session_id="sess_demo_brooklyn",
)


# ------------------------------------------------------------------------------
# 2. Svalbard Arctic (Extreme Cold, Environmental Regs, Polar Wildlife, Rescue)
# ------------------------------------------------------------------------------
_SVALBARD_SCRIPT = """EXT. SVALBARD GLACIER OUTLET - TWILIGHT

A blinding arctic blizzard sweeps across the crevasse field. Temperature: -32°C.

ELENA (40s), bundled in expedition-grade survival parkas, maneuvers a twin-track snowmobile across fragile sea ice. Beside her rides JONAS, carrying an emergency flare rifle.

ELENA
The satellite relay went dark three hours ago. If the sea ice fractures before we reach the fjord station, we're stranded.

Wind screams at 50 knots, reducing visibility to less than ten meters. In the whiteout distance, the silhouette of an apex arctic predator pauses against the glacial moraine.

JONAS
(checks flare rifle)
Governor's office protocol requires non-lethal dispersal. Maintain distance!"""

_SVALBARD_FALLBACK = ParallelSearchResponse(
    search_id="par_demo_svalbard_02",
    results=[
        ParallelResultItem(
            url="https://www.sysselmesteren.no/en/travel-and-holidays/regulations-for-field-activities-and-travel-in-svalbard/",
            title="Governor of Svalbard - Regulations for Field Activities, Filming, and Safety",
            publish_date="2024-03-01",
            excerpts=[
                "Commercial film productions operating outside Management Area 10 must notify the Governor of Svalbard at least 4 to 8 weeks prior to arrival.",
                "Mandatory search and rescue (SAR) insurance and approved safety plans covering polar bear defense, crevasse rescue, and emergency satellite comms are legally mandated.",
                "Approaching or intentionally disturbing polar bears is strictly prohibited under the Svalbard Environmental Protection Act.",
            ],
        ),
        ParallelResultItem(
            url="https://www.thebroadcastbridge.com/content/entry/17845/shooting-in-sub-zero-conditions-equipment-protection-guide",
            title="Production Guide: Camera and Battery Performance in Sub-Zero Arctic Environments",
            publish_date="2023-11-15",
            excerpts=[
                "Lithium-ion batteries experience 60-80% capacity drop when ambient temperatures fall below -25°C. Heated battery jackets and internal sensor warmers are necessary.",
                "Condensation precautions when transitioning gear between freezing exteriors and heated shelters require airtight seal bags with silica packs to prevent lens fogging.",
            ],
        ),
    ],
    session_id="sess_demo_svalbard",
)


# ------------------------------------------------------------------------------
# 3. Savannah Pyro (Historic Preservation, Fire Permits, Pyrotechnics, Shrapnel)
# ------------------------------------------------------------------------------
_SAVANNAH_SCRIPT = """EXT. MONTEREY SQUARE (SAVANNAH) - NIGHT

Spanish moss hangs heavy from century-old live oaks surrounding historic brick mansions. Gas lamps flicker in the humid night air.

MARCUS (50s) retreats behind the iron fence of a 19th-century townhouse as gunfire echoes through the cobblestone square.

A delivery van parked along the curb ignites with an explosive fireball, shattering safety glass and throwing a shockwave against the brick facades.

MARCUS
Contain the perimeter! Watch the dry timber!

A secondary pyrotechnic blast erupts from the carriage house, showering embers over the historic square."""

_SAVANNAH_FALLBACK = ParallelSearchResponse(
    search_id="par_demo_savannah_03",
    results=[
        ParallelResultItem(
            url="https://www.savannahga.gov/543/Special-Events-Filming-Permits",
            title="City of Savannah Special Events & Film Office - Pyrotechnics Permitting Protocol",
            publish_date="2023-12-05",
            excerpts=[
                "Open flame, gunfire simulation, and pyrotechnic special effects inside the Savannah Historic Landmark District require approval from both the Film Office and Savannah Fire Marshal.",
                "Pyrotechnic permit applications must be submitted at least 21 business days in advance with a detailed blast plan, certificate of insurance naming the City of Savannah ($5M aggregate), and licensed pyrotechnic operator credentials.",
                "Historic live oaks and historic facade protection plans must be approved by the City Arborist and Historic District Board of Review prior to detonating explosive devices.",
            ],
        ),
        ParallelResultItem(
            url="https://georgia.org/industries/film-entertainment/fire-safety-guidelines",
            title="Georgia Film Commission - Fire Safety and Pyrotechnic Regulations for Filming",
            publish_date="2024-01-22",
            excerpts=[
                "Standby fire personnel (minimum one dedicated engine company and two certified safety officers) are mandatory for explosive practical effects in residential historic zones.",
                "Decibel and percussive shockwave limits apply to prevent mortar crumbling and window fracturing in pre-1900 unreinforced masonry structures.",
            ],
        ),
    ],
    session_id="sess_demo_savannah",
)


_STAGE_FALLBACK = ParallelSearchResponse(
    search_id="par_demo_stage_01",
    results=[
        ParallelResultItem(
            url="https://www.filmla.com/production-permits/",
            title="FilmLA - Studio Lot and Certified Sound Stage Production Permits",
            publish_date="2025-02-11",
            excerpts=[
                "Filming conducted entirely within a certified sound stage on a permitted "
                "studio lot in Los Angeles is covered by the lot's standing permit and does "
                "not require a separate location film permit."
            ],
        ),
    ],
)


_LA_STREET_FALLBACK = ParallelSearchResponse(
    search_id="par_demo_la_street_01",
    results=[
        ParallelResultItem(
            url="https://www.filmla.com/production-permits/",
            title="FilmLA - Film Permit Requirements for Los Angeles Public Streets",
            publish_date="2025-03-04",
            excerpts=[
                "Filming on a public street or sidewalk in the City of Los Angeles requires "
                "a film permit issued by FilmLA. Applications should be submitted at least "
                "three business days in advance, and proof of general liability insurance "
                "naming the City as additional insured is mandatory."
            ],
        ),
        ParallelResultItem(
            url="https://ladot.lacity.gov/",
            title="LADOT - Traffic Control for Filming and Intermittent Traffic Control",
            publish_date="2024-11-19",
            excerpts=[
                "Intermittent traffic control in Los Angeles must be performed by qualified "
                "traffic control personnel working to an approved traffic control plan. "
                "Pedestrian access along the sidewalk must be maintained or an approved "
                "detour provided."
            ],
        ),
    ],
)


# ------------------------------------------------------------------------------
# Scenario Registry
# ------------------------------------------------------------------------------
_SCENARIOS: Dict[str, DemoScenario] = {
    "brooklyn-drone-chase": DemoScenario(
        id="brooklyn-drone-chase",
        title="Brooklyn Bridge Drone Chase",
        logline="Tactical FPV drone dogfight over moving bridge traffic and the East River at night.",
        script_text=_BROOKLYN_SCRIPT,
        target_categories=[
            DependencyCategory.PERMITS_AND_LEGAL,
            DependencyCategory.SAFETY_AND_STUNTS,
            DependencyCategory.LOCATIONS_AND_ACCESS,
        ],
        primary_dependency="Low-altitude night drone flight over active vehicular traffic on iconic bridge.",
        sample_search_objective="Verify FAA Part 107 waiver and NYC MOME permit requirements for night drone filming over traffic",
        sample_search_queries=[
            "NYC MOME UAS drone permit requirements night filming",
            "FAA Part 107.39 waiver flight over moving vehicles",
            "Brooklyn Bridge filming permits DOT NYPD lead time",
        ],
        fallback_response=_BROOKLYN_FALLBACK,
    ),
    "svalbard-arctic": DemoScenario(
        id="svalbard-arctic",
        title="Svalbard Arctic Extraction",
        logline="High-speed snowmobile recovery mission on remote glacier sea ice in sub-zero whiteout.",
        script_text=_SVALBARD_SCRIPT,
        target_categories=[
            DependencyCategory.WEATHER_AND_ENVIRONMENT,
            DependencyCategory.EQUIPMENT_AND_GEAR,
            DependencyCategory.SAFETY_AND_STUNTS,
        ],
        primary_dependency="Filming in -30°C blizzard conditions on sea ice with polar wildlife safety mandates.",
        sample_search_objective="Verify Governor of Svalbard filming regulations, polar bear defense mandates, and arctic camera gear limitations",
        sample_search_queries=[
            "Governor of Svalbard field activity filming regulations permit",
            "Svalbard polar bear safety requirements filming commercial",
            "sub zero camera battery failure -30C filming solutions",
        ],
        fallback_response=_SVALBARD_FALLBACK,
    ),
    "savannah-pyro": DemoScenario(
        id="savannah-pyro",
        title="Savannah Historic District Pyrotechnics",
        logline="Nocturnal vehicle detonation and shootout within historic brick square with Spanish moss oaks.",
        script_text=_SAVANNAH_SCRIPT,
        target_categories=[
            DependencyCategory.PERMITS_AND_LEGAL,
            DependencyCategory.SAFETY_AND_STUNTS,
            DependencyCategory.LOCATIONS_AND_ACCESS,
        ],
        primary_dependency="High-impact vehicle explosion in 19th-century unreinforced masonry historic square.",
        sample_search_objective="Verify Savannah Fire Department pyrotechnic permit timeline and Historic District structural protections",
        sample_search_queries=[
            "Savannah Fire Department pyrotechnic permit film production timeline",
            "Savannah Historic District filming regulations explosives open flame",
            "Georgia film commission pyrotechnic operator requirements standby fire truck",
        ],
        fallback_response=_SAVANNAH_FALLBACK,
    ),
    "stage-interior-dialogue": DemoScenario(
        id="stage-interior-dialogue",
        title="Soundstage Interior Dialogue",
        logline="A two-hander dialogue scene shot entirely on a permitted, controlled studio sound stage.",
        script_text=_STAGE_SCRIPT,
        target_categories=[
            DependencyCategory.LOCATIONS_AND_ACCESS,
        ],
        primary_dependency="Controlled interior stage work with no exterior, effects or public exposure.",
        sample_search_objective="Verify studio lot sound stage filming permit requirements",
        sample_search_queries=[
            "certified sound stage studio lot filming permit Los Angeles",
            "interior stage production permit requirements California",
        ],
        fallback_response=_STAGE_FALLBACK,
    ),
    "los-angeles-controlled-street-dialogue": DemoScenario(
        id="los-angeles-controlled-street-dialogue",
        title="LA Controlled Street Dialogue",
        logline="A two-hander walk-and-talk on a permitted Los Angeles block with approved traffic control.",
        script_text=_LA_STREET_SCRIPT,
        target_categories=[
            DependencyCategory.LOCATIONS_AND_ACCESS,
        ],
        primary_dependency="Permitted public-street filming with intermittent traffic control and pedestrian management.",
        sample_search_objective="Verify Los Angeles street filming permit and traffic control requirements",
        sample_search_queries=[
            "FilmLA public street film permit requirements Los Angeles",
            "LADOT intermittent traffic control filming approved plan Los Angeles",
        ],
        fallback_response=_LA_STREET_FALLBACK,
    ),
}


def get_sample_scenarios() -> List[DemoScenario]:
    """Returns the list of all curated demo scenarios."""
    return list(_SCENARIOS.values())


def get_scenario_by_id(scenario_id: str) -> Optional[DemoScenario]:
    """Retrieves a specific scenario by its slug ID."""
    return _SCENARIOS.get(scenario_id)


def get_fallback_research(objective: str) -> Optional[ParallelSearchResponse]:
    """Finds the most relevant fallback fixture for demo/offline resilience based on objective keywords."""
    obj_lower = objective.lower()
    if any(k in obj_lower for k in ["drone", "brooklyn", "faa", "traffic", "flight"]):
        return _BROOKLYN_FALLBACK
    elif any(k in obj_lower for k in ["svalbard", "arctic", "polar", "snow", "ice", "cold"]):
        return _SVALBARD_FALLBACK
    elif any(k in obj_lower for k in ["savannah", "pyro", "fire", "explosion", "historic", "blast"]):
        return _SAVANNAH_FALLBACK
    elif any(k in obj_lower for k in ["sound stage", "soundstage", "studio lot", "interior stage"]):
        return _STAGE_FALLBACK
    elif any(k in obj_lower for k in ["street", "traffic control", "pedestrian", "sidewalk"]):
        return _LA_STREET_FALLBACK
    return _BROOKLYN_FALLBACK  # sensible default
