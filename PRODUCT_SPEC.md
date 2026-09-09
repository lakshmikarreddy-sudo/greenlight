# Greenlight — Product Specification
**AI Production-Intelligence Agent for Cinema**
*Google Cloud Agentic Cinema Hackathon*

---

## 1. Product Vision & Value Proposition

**Greenlight** bridges the gap between creative storytelling and physical film production reality.

Every film starts as a script, but turning that script into a physical shoot requires a grueling breakdown process:
- *Can we shoot this sequence on location?*
- *Do we need FAA waivers for the drone sequence?*
- *What is the fire marshal permitting lead time for that explosion?*
- *Will the river be frozen during our December shoot?*

Greenlight ingests screenplays, uses **Gemini 2.5 Flash on Google Cloud Vertex AI** to extract every production constraint, and autonomously deploys **Parallel Search API** at runtime to investigate real-world permits, legal requirements, environmental windows, and logistical hurdles.

It outputs the **"Greenlight Production Brief"** — an executive scorecard and interactive roadmap with categorized risk badges (🟢 **GREEN**, 🟡 **YELLOW**, 🔴 **RED**) backed by cited external evidence.

---

## 2. Target User Personas

| Persona | Role | Primary Pain Point Solved |
|---|---|---|
| **Line Producer / UPM** | Unit Production Manager | Spends days manually researching local film commission regulations, union constraints, and safety guidelines. |
| **1st Assistant Director (1st AD)** | Scheduling & Logistics | Struggles to forecast scheduling bottlenecks (e.g., weather windows, day/night ratios, special equipment arrival). |
| **Executive Producer / Financier** | Greenlight Decisions & Bonding | Needs instant visibility into high-liability risks (pyrotechnics, child actors, remote filming) before releasing funds. |
| **Independent Filmmaker** | Writer / Director / Producer | Lacks the budget for an army of production coordinators; needs Hollywood-grade breakdown intelligence on demand. |

---

## 3. Core Features & Capabilities

### Feature 1: Multi-Format Screenplay Ingestion
- **Formats Supported**: Native PDF (`.pdf`), Fountain screenplay format (`.fountain`), Plain Text (`.txt`).
- **Direct Text Input**: Paste raw screenplay scenes directly into the browser.
- **Curated Demo Library**: Preloaded one-click scenes for instant hackathon demonstrations:
  - *Demo 1: The Brooklyn Bridge Drone Intercept* (Urban airspace, night permits, NYPD coordination).
  - *Demo 2: Svalbard Arctic Extraction* (Remote ice logistics, polar bear safety protocols, extreme cold gear).
  - *Demo 3: Savannah Historic District Pyrotechnics* (Preservation society rules, fire department permits, street closure ordinances).

### Feature 2: Automated Entity & Production Dependency Extraction
Powered by Google ADK and Gemini 2.5 on Vertex AI:
- **Scene Details**: Scene numbers, sluglines (`INT./EXT.`, `LOCATION`, `TIME OF DAY`), page counts.
- **Characters & Cast**: Principal cast, speaking roles, background extras, stunts/doubles, child actors.
- **Physical Elements**: Vehicles, period props, practical weapons, wardrobe changes, special makeup (SFX).
- **Environmental & Set Requirements**: Night exteriors, rain/fog/snow machines, underwater or high-altitude shoots.
- **Logistical Flags**: Sound issues, tight turnaround times, hazardous stunts.

### Feature 3: Autonomous Real-World Research via Parallel Search API
- The agent isolates dependencies with unknown real-world feasibility.
- At runtime, the ADK Agent executes the `parallel_search_tool` calling `https://api.parallel.ai/v1/search`.
- Uses high-density web search to retrieve authoritative facts:
  - Municipal film commission guidelines.
  - FAA / CAA airspace and drone flight restrictions.
  - SAG-AFTRA and local union turnaround and safety standards.
  - Historical weather patterns and daylight hour data.
- Excerpts and URLs are preserved for source grounding.

### Feature 4: Three-Tier Production Risk Engine
Every production element is scored according to a transparent risk rubric:
- 🟢 **GREEN (Low Concern)**:
  - Standard studio/interior setup.
  - Readily available equipment.
  - Routine permitting (< 7 days) with negligible schedule risk.
- 🟡 **YELLOW (Review Required)**:
  - Moderate permitting timeline (14–30 days).
  - Specialized crew or safety monitors required (e.g., water safety, stunt coordinator).
  - Seasonal or environmental variance requiring backup shoot dates.
- 🔴 **RED (Critical Production Hazard / Blocker)**:
  - Legal prohibitions or strict municipal bans (e.g., unauthorized drone swarms in restricted airspace).
  - Severe safety hazards without certified specialists.
  - Extreme lead times (> 60 days) threatening production schedule.
  - Extreme budget inflation trap.

### Feature 5: The "Greenlight Production Brief"
The final structured intelligence report delivered to the filmmaker:
1. **Executive Production Scorecard**:
   - Overall Viability Score (e.g. `78/100 - CONDITIONAL GREENLIGHT`).
   - Risk Distribution breakdown (e.g. `12 Green`, `4 Yellow`, `2 Red`).
   - High-level synopsis and budget/schedule impact estimate.
2. **Production Dependency Matrix**:
   - Filterable by category: *Locations*, *Stunts & SFX*, *Permits & Legal*, *Cast & Crew*, *Weather & Environment*.
3. **Risk & Mitigation Playbook**:
   - Specific, concrete recommended actions for every Yellow and Red item.
4. **External Intelligence & Evidence Trail**:
   - Live citations with clickable source links and verbatim Parallel excerpts proving regulatory claims.

---

## 4. UI Screens & User Experience

The application is delivered as a single-page web interface with a **Dark Cinematic Aesthetic** inspired by film slate monitors and premium post-production tools.

### Screen 1: Hero & Ingestion Hub
- **Header**: "GREENLIGHT // AI Production Intelligence" with live indicators for Google Cloud Vertex AI and Parallel Search status.
- **Upload Dropzone**: Drag-and-drop screenplay PDF or text file.
- **Demo Presets Bar**: One-click pills: `[⚡ Brooklyn Drone Chase]` `[❄️ Svalbard Arctic]` `[🔥 Savannah Pyro]`.
- **Primary CTA**: "RUN PRODUCTION BREAKDOWN" button with glowing amber/emerald pulse.

### Screen 2: Real-Time Agent Telemetry (Streaming Drawer)
- Slides open during agent execution.
- Displays the live agent thoughts via Server-Sent Events (SSE):
  - `[00:01.2] Gemini 2.5 parsing scene sluglines...`
  - `[00:02.4] Identified 3 high-uncertainty dependencies.`
  - `[00:03.1] Parallel Search API invoked -> Query: "NYC drone filming waiver night FAA"`
  - `[00:04.8] Received 4 source excerpts from api.parallel.ai.`
  - `[00:05.9] Synthesizing final Greenlight Production Brief...`

### Screen 3: The Production Brief Dashboard
- **Top Row**:
  - **Verdict Card**: Large status pill (e.g., `🟡 CONDITIONAL GREENLIGHT - 3 HAZARDS DETECTED`).
  - **Metric Badges**: Total Scenes Analyzed, Red Flags, Yellow Flags, External Citations.
- **Main View (Tabbed Interface)**:
  - **Tab 1: Executive Briefing**: Summary narrative, critical paths, and overall feasibility verdict.
  - **Tab 2: Interactive Scene Breakdown**: Scene-by-scene card deck with cast, props, and location tags.
  - **Tab 3: Risk & Mitigation Matrix**: Accordion of Yellow & Red findings with recommended filmmaker actions.
  - **Tab 4: Parallel Evidence Ledger**: Complete list of research sources, URLs, and verified regulatory excerpts.
- **Export Action**:
  - "Download Brief (.PDF / .MD)" and "Copy Executive Summary".

---

## 5. Screenplay Breakdown Data Schema

```json
{
  "project_title": "string",
  "screenplay_summary": "string",
  "overall_status": "GREEN | YELLOW | RED",
  "readiness_score": 82,
  "scenes": [
    {
      "scene_number": 1,
      "slugline": "EXT. BROOKLYN BRIDGE - NIGHT",
      "summary": "A high-speed drone chase over the East River.",
      "characters": ["AGENT VANCE", "DRONE PILOT"],
      "props_and_wardrobe": ["Tactical surveillance gear", "Custom FPV controller"],
      "stunts_and_sfx": ["FPV drone flyby under suspension cables"],
      "environmental_factors": ["High winds over water", "Night lighting"],
      "dependencies": [
        {
          "element": "Low-altitude night drone flight over active bridge",
          "category": "PERMITS_AND_LEGAL",
          "status": "RED",
          "risk_description": "FAA Part 107 prohibits drone flights over moving traffic without a Part 107.39 waiver and NYPD Film Office approval.",
          "parallel_evidence": {
            "query": "NYC drone filming waiver night FAA Brooklyn Bridge",
            "source_title": "NYC Mayor's Office of Media and Entertainment - UAS Guidelines",
            "source_url": "https://www.nyc.gov/site/mome/permits/uas-guidelines.page",
            "excerpt": "Uncrewed Aircraft Systems (UAS) permits in New York City require at least 30-day notice and approval from both NYPD and DOT."
          },
          "recommended_action": "Apply for FAA Part 107.39 waiver 60 days in advance or replace exterior bridge flight with a CGI plate shot from a stationary tugboat."
        }
      ]
    }
  ],
  "executive_summary": "string",
  "top_risks": ["string"],
  "recommended_next_steps": ["string"]
}
```

---

## 6. Hackathon Acceptance Criteria

| Criteria | Acceptance Condition |
|---|---|
| **Gemini via Vertex AI** | Uses `gemini-2.5-flash` through Google ADK pointing to project `greenlight-ac-2026-lkr` and region `us-central1`. |
| **ADK Orchestration** | Agent, tool registration, and session execution are managed via `google-adk`. |
| **Parallel Search API** | `https://api.parallel.ai/v1/search` is actively invoked at runtime with realistic film production queries. |
| **No Phantom Mentions** | Real search results (URLs, excerpts) are displayed and linked in the generated brief. |
| **Three-Tier Status** | Every production dependency is clearly categorized as GREEN, YELLOW, or RED with actionable justifications. |
| **Simplicity & Polish** | Single-command launch (`python main.py` or `uvicorn`), zero database setup, zero complex microservices, immediate demo readiness. |
