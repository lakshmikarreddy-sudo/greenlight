"""FastAPI application exposing Greenlight analysis endpoints and SSE streaming.

Endpoints:
  GET /api/health
  GET /api/samples
  POST /api/analyze  (returns Server-Sent Events stream)

This module routes ingestion through `ScriptParser` and orchestrates the
`GreenlightOrchestrator` for semantic analysis. It intentionally does not
perform PDF parsing locally and will return a clear PDF_REQUIRES_GEMINI
fallback when PDFs are provided.
"""
from typing import AsyncGenerator, Dict, Any, Optional
import json
import asyncio

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from server.config import settings
from server.services.script_parser import ScriptParser, ParseError, PDFRequiresGeminiError
from server.services.sample_library import get_sample_scenarios, get_scenario_by_id
from server.agent.greenlight_agent import GreenlightOrchestrator
from server.agent.events import create_event, EventType, AgentEvent
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


# Application instance
app = FastAPI(title=settings.app_name, description=settings.app_description)


# Mount static directory for the frontend
app.mount("/static", StaticFiles(directory="server/static"), name="static")


@app.get("/")
async def index():
    return FileResponse("server/static/index.html")

# Development-friendly CORS (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse_format(event: AgentEvent) -> str:
    payload = event.model_dump()
    # Ensure JSON is safe for SSE
    data = json.dumps(payload, ensure_ascii=False)
    # Use the enum value (e.g. 'analysis_started') for the SSE event name
    ev_name = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
    return f"event: {ev_name}\n" + f"data: {data}\n\n"


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    # Do not include secrets in health output
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "model_name": settings.model_name,
        "vertex_configured": settings.is_vertex_configured,
        "parallel_configured": settings.is_parallel_configured,
        "demo_mode": settings.demo_mode,
    }


@app.get("/api/samples")
async def samples():
    scenarios = get_sample_scenarios()
    return [s.model_dump() for s in scenarios]


@app.post("/api/analyze")
async def analyze(request: Request):
    """Accepts JSON body with either:
      - `text` (plain screenplay text)
      - `format`: 'fountain' to parse as Fountain
      - `sample_id` to run a curated demo
      - `pdf` -> triggers PDFRequiresGeminiError fallback

    Returns an SSE stream of AgentEvent objects.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    # PDF boundary handling
    if body.get("pdf"):
        # Immediately return SSE error indicating Gemini is required
        ev = create_event(
            event_type=EventType.ANALYSIS_ERROR,
            stage="INGESTION",
            message="PDF input requires Gemini native understanding (PDF_REQUIRES_GEMINI)",
            data={"pdf_requires_gemini": True},
        )

        async def _pdf_stream() -> AsyncGenerator[str, None]:
            yield _sse_format(ev)

        return StreamingResponse(_pdf_stream(), media_type="text/event-stream")

    sample_id = body.get("sample_id")
    script_text: Optional[str] = None
    project_title = body.get("project_title") or "API Project"
    fmt = body.get("format", "plain")

    if sample_id:
        scenario = get_scenario_by_id(sample_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Sample not found")
        script_text = scenario.script_text
        project_title = scenario.title
    else:
        script_text = body.get("text")

    if not script_text:
        raise HTTPException(status_code=400, detail="Missing 'text' or 'sample_id' in request")

    # Route ingestion through ScriptParser once and obtain a ScreenplayBreakdown
    try:
        if fmt == "fountain":
            breakdown = ScriptParser.parse_fountain(script_text, project_title=project_title)
        else:
            breakdown = ScriptParser.parse_text(script_text, project_title=project_title)
    except ParseError as pe:
        raise HTTPException(status_code=400, detail=str(pe))
    except PDFRequiresGeminiError:
        ev = create_event(
            event_type=EventType.ANALYSIS_ERROR,
            stage="INGESTION",
            message="PDF input requires Gemini native understanding (PDF_REQUIRES_GEMINI)",
            data={"pdf_requires_gemini": True},
        )

        async def _pdf_stream2() -> AsyncGenerator[str, None]:
            yield _sse_format(ev)

        return StreamingResponse(_pdf_stream2(), media_type="text/event-stream")

    orchestrator = GreenlightOrchestrator()

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Stream orchestrator events directly as SSE using the pre-parsed breakdown
            async for evt in orchestrator.run_analysis_async(script_text, project_title=project_title, breakdown=breakdown):
                # evt is an AgentEvent
                try:
                    yield _sse_format(evt)
                except Exception:
                    # Emit sanitized error event
                    err = create_event(
                        event_type=EventType.ANALYSIS_ERROR,
                        stage="STREAM",
                        message="Failed to serialize event",
                        data=None,
                    )
                    yield _sse_format(err)
                # After brief generation, also emit the full serialized brief if available
                try:
                    if evt.event_type == EventType.BRIEF_GENERATED and getattr(orchestrator, "latest_brief", None) is not None:
                        brief_obj = orchestrator.latest_brief
                        # Safely serialize the Pydantic model to dict
                        brief_payload = brief_obj.model_dump() if hasattr(brief_obj, "model_dump") else None
                        if brief_payload:
                            brief_event = {
                                "event_type": "brief",
                                "stage": "BRIEF",
                                "message": "Full Greenlight Production Brief",
                                "timestamp": None,
                                "data": brief_payload,
                            }
                            # Emit as a custom SSE event named 'brief'
                            ev_name = "brief"
                            data = json.dumps(brief_event, ensure_ascii=False)
                            yield f"event: {ev_name}\n" + f"data: {data}\n\n"
                except Exception:
                    # If brief serialization fails, continue streaming other events
                    pass
        except Exception:
            err = create_event(
                event_type=EventType.ANALYSIS_ERROR,
                stage="SERVER",
                message="Internal server error during analysis",
                data=None,
            )
            yield _sse_format(err)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
