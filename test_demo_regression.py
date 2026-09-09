"""Greenlight demo regression/UAT smoke test.

Run from the project root while the FastAPI server is running:

    .\.venv\Scripts\python.exe test_demo_regression.py

This test validates:
- backend health
- all three curated scenarios
- final SSE brief emission
- RED/YELLOW/GREEN decision
- readiness score
- dependencies and scenes
- frontend contract
- pipeline order
- Reset Demo ownership of cache clearing
- Paste Screenplay presence
- Fountain removal
- scenario-result persistence implementation

It intentionally does NOT modify backend or greenlight_agent code.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8889"

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "server" / "static"
INDEX = STATIC / "index.html"
APP = STATIC / "js" / "app.js"

REQUIRED_STAGES = [
    "INGEST",
    "EXTRACT",
    "TRIAGE",
    "RESEARCH",
    "ASSESS",
    "MITIGATE",
    "GREENLIGHT",
]

REQUIRED_SAMPLES = {
    "brooklyn-drone-chase",
    "svalbard-arctic",
    "savannah-pyro",
    "stage-interior-dialogue",
    "los-angeles-controlled-street-dialogue",
}


def fail(message: str):
    print(f"\nFAIL: {message}")
    sys.exit(1)


def get_json(path: str):
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        fail(f"{path} unavailable: {exc}")


def post_sse(payload: dict):
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        BASE + "/api/analyze",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        fail(f"/api/analyze failed for {payload}: {exc}")

    events = []
    current_event = None
    current_data = []

    for line in raw.splitlines():
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()

        elif line.startswith("data:"):
            current_data.append(
                line.split(":", 1)[1].lstrip()
            )

        elif not line.strip() and current_data:
            payload_text = "\n".join(current_data)

            try:
                parsed = json.loads(payload_text)
            except json.JSONDecodeError:
                parsed = {"raw": payload_text}

            events.append((current_event, parsed))

            current_event = None
            current_data = []

    return events


def assert_file_exists(path: Path):
    if not path.exists():
        fail(f"required file missing: {path}")


def check_frontend_contract():
    assert_file_exists(INDEX)
    assert_file_exists(APP)

    index = INDEX.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    required_index_tokens = [
        'id="scenarioButtons"',
        'id="tabDemo"',
        'id="tabPaste"',
        'id="resetBtn"',
        'id="analyzeBtn"',
        'id="eventLog"',
        'id="pipelineList"',
        'id="overallStatus"',
        'id="readinessScore"',
        'id="topRisksList"',
        'id="evidenceList"',
        'id="decisionChainList"',
        'id="sceneBreakdownList"',
    ]

    for token in required_index_tokens:
        if token not in index:
            fail(f"frontend missing UI contract: {token}")

    # Competition UI should not expose Fountain.
    if "Fountain" in index:
        fail("Fountain is still exposed in index.html")

    if "tabFountain" in app:
        fail("obsolete Fountain implementation remains in app.js")

    # Native select is not part of the judging UI.
    if "<select" in index.lower():
        fail("native <select> found in competition UI")

    # Pipeline order must remain exact.
    positions = []

    for stage in REQUIRED_STAGES:
        token = f'data-stage="{stage}"'
        pos = index.find(token)

        if pos < 0:
            fail(f"pipeline stage missing: {stage}")

        positions.append(pos)

    if positions != sorted(positions):
        fail("pipeline stages are out of order")

    # Reset must be the only place that clears result cache.
    if "resultCache.clear()" not in app:
        fail("Reset Demo does not clear result cache")

    if "resetBtn" not in app:
        fail("Reset Demo button is not wired in app.js")

    if "scenarioCache.clear()" in app:
        fail("obsolete scenarioCache implementation remains")

    # Scenario cache should exist.
    if "resultCache" not in app:
        fail("scenario result cache is missing")

    # Paste Screenplay must remain available.
    if "Paste Screenplay" not in index:
        fail("Paste Screenplay option missing")

    if "paste" not in app.lower():
        fail("Paste Screenplay handling appears to be missing")

    # The UI must distinguish selection from completed analysis.
    if "selected" not in app.lower():
        fail("scenario selection state appears to be missing")

    print("PASS: frontend files exist")
    print("PASS: frontend UI contract")
    print("PASS: Fountain removed from competition UI")
    print("PASS: Paste Screenplay present")
    print("PASS: pipeline stages present and ordered")
    print("PASS: scenario result cache present")
    print("PASS: Reset Demo owns cache clearing")

    check_render_contract()


def _strip_js_comments(app: str) -> str:
    """Drop JS comments so structural checks match code, not prose.

    Explanatory comments legitimately quote the very patterns some of these
    checks forbid, so comments must not be searched.
    """

    app = re.sub(r"/\*[\s\S]*?\*/", " ", app)
    # Leave protocol text such as https:// alone.
    app = re.sub(r"(?<!:)//[^\n]*", " ", app)

    return app


def _function_body(app: str, name: str) -> str:
    """Return a top-level function's source, located by brace matching.

    Deliberately structural: this does not depend on line numbers, indentation
    or formatting, only on the function existing and being brace-balanced.
    """

    marker = f"function {name}("
    start = app.find(marker)

    if start < 0:
        fail(f"{name}() not found in app.js")

    index = app.index("{", start)
    depth = 0

    while index < len(app):
        if app[index] == "{":
            depth += 1
        elif app[index] == "}":
            depth -= 1

            if depth == 0:
                return app[start:index + 1]

        index += 1

    fail(f"{name}() is not brace-balanced in app.js")


def check_render_contract():
    """The `brief` SSE event is the authoritative final result.

    These guard the browser-level defect where Agent Activity showed the whole
    pipeline but the Production Decision panel stayed empty, because the brief
    payload was read from the raw SSE `data` string instead of the decoded
    object.
    """

    app = _strip_js_comments(APP.read_text(encoding="utf-8"))

    # The brief handler must cache and render on the spot. It must not defer
    # to a later analysis_completed event.
    match = re.search(r"case 'brief':([\s\S]*?)break;", app)

    if not match:
        fail("no `case 'brief':` handler found in the SSE event switch")

    brief_case = match.group(1)

    if "renderBrief(" not in brief_case:
        fail("`brief` event handler does not call renderBrief()")

    if "cache.brief" not in brief_case:
        fail("`brief` event handler does not set cache.brief")

    if not re.search(r"cache\.running\s*=\s*false", brief_case):
        fail("`brief` event handler does not set cache.running = false")

    print("PASS: `brief` handler caches, clears running and renders")

    # The brief payload must be normalized, never read off the raw SSE string.
    # streamAnalyze() puts the undecoded JSON text in evt.data, and a non-empty
    # string is truthy, so `brief?.data || {}` silently yields a string and
    # every field read comes back undefined.
    if re.search(r"brief\??\.data\s*\|\|", app):
        fail(
            "renderBrief reads the raw SSE `data` string; "
            "it must use the decoded payload"
        )

    if "function briefData(" not in app:
        fail("brief payload normalizer (briefData) is missing")

    if "parsed" not in _function_body(app, "briefData"):
        fail("briefData() does not consider the decoded `parsed` payload")

    print("PASS: brief payload is normalized before rendering")

    # renderBrief must populate every headline field of the decision panel.
    render_source = _function_body(app, "renderBrief")

    if "renderBriefContent" in render_source:
        render_source += _function_body(app, "renderBriefContent")

    required_outputs = [
        "overallStatus",
        "readinessScore",
        "greenCount",
        "yellowCount",
        "redCount",
        "sceneCount",
    ]

    missing = [
        target for target in required_outputs
        if target not in render_source
    ]

    if missing:
        fail(f"renderBrief does not populate: {missing}")

    # No silent failure: a throw must be logged and surfaced in the UI.
    if "console.error" not in render_source:
        fail("renderBrief does not log rendering failures")

    if "handleAnalysisError" not in render_source:
        fail("renderBrief does not surface a visible error when it throws")

    print("PASS: renderBrief populates the decision panel and fails loudly")

    # A completed cached result must re-render through the same path.
    render_cached = _function_body(app, "renderCached")

    if "renderBrief(" not in render_cached:
        fail("renderCached does not re-render a completed brief")

    # Selecting a scenario restores; it never clears another scenario's cache.
    select_scenario = _function_body(app, "selectScenario")

    if "renderCached(" not in select_scenario:
        fail("selectScenario does not restore through renderCached()")

    if "resultCache.delete(" in app:
        fail("resultCache.delete() found; Reset Demo owns cache clearing")

    if app.count("resultCache.clear()") != 1:
        fail("resultCache.clear() must appear exactly once (Reset Demo)")

    reset_at = app.find("resetBtn?.addEventListener")
    clear_at = app.find("resultCache.clear()")

    if reset_at < 0 or clear_at < reset_at:
        fail("resultCache.clear() is not inside the Reset Demo handler")

    print("PASS: cached results restore on selection and only Reset clears them")

    # Analyze must return to an enabled, runnable state after completion.
    if "'Analyzed'" in app or '"Analyzed"' in app:
        fail("Analyze is left in a disabled 'Analyzed' state after completion")

    if not re.search(r"analyzeBtn\.disabled\s*=\s*false", render_source):
        fail("renderBrief does not re-enable the Analyze button")

    print("PASS: Analyze is enabled again after a completed analysis")

    # The readiness explanation must be present, collapsed, and additive.
    index = INDEX.read_text(encoding="utf-8")
    for token in ("toggleExplain", "explainPanel", "explainSteps", "explainCheck"):
        if token not in index:
            fail(f"explainability surface missing from index.html: {token}")

    if 'id="explainPanel" class="explain-panel hidden"' not in index:
        fail("explanation panel must start collapsed")

    if "buildExplanation" not in app or "renderExplanation" not in app:
        fail("app.js does not render the readiness explanation")

    explain = STATIC / "js" / "explain.js"
    if not explain.exists():
        fail("server/static/js/explain.js is missing")

    explain_src = _strip_js_comments(explain.read_text(encoding="utf-8"))
    if "signal_provenance" not in explain_src:
        fail("explanation basis must be derived from evidence provenance")
    if "INHERENT" not in explain_src:
        fail("explanation must distinguish inherent-risk baselines from evidence")

    print("PASS: readiness explanation is present, collapsed and provenance-aware")


def check_backend():
    health = get_json("/api/health")

    if not health:
        fail("/api/health returned empty response")

    samples = get_json("/api/samples")

    if not isinstance(samples, list):
        fail("/api/samples did not return a list")

    ids = {item.get("id") for item in samples}

    missing = REQUIRED_SAMPLES - ids

    if missing:
        fail(f"missing curated samples: {sorted(missing)}")

    print("PASS: /api/health")
    print("PASS: /api/samples — all 3 curated scenarios")


def check_scenario(sample_id: str):
    events = post_sse({"sample_id": sample_id})

    if not events:
        fail(f"{sample_id}: no SSE events received")

    names = [name for name, _ in events if name]

    if "brief" not in names:
        fail(f"{sample_id}: no final brief SSE event")

    brief_payload = next(
        data
        for name, data in reversed(events)
        if name == "brief"
    )

    data = brief_payload.get("data", brief_payload)

    scorecard = data.get("scorecard", {})

    status = (
        scorecard.get("overall_status")
        or data.get("overall_status")
    )

    score = scorecard.get("readiness_score")

    dependencies = data.get(
        "assessed_dependencies",
        []
    )

    scenes = data.get(
        "scenes",
        []
    )

    if status not in {"RED", "YELLOW", "GREEN"}:
        fail(
            f"{sample_id}: invalid decision status "
            f"{status!r}"
        )

    if not isinstance(score, (int, float)):
        fail(
            f"{sample_id}: missing readiness score"
        )

    if not 0 <= score <= 100:
        fail(
            f"{sample_id}: readiness score outside 0-100: "
            f"{score}"
        )

    if not isinstance(dependencies, list):
        fail(
            f"{sample_id}: assessed_dependencies "
            "is not a list"
        )

    if not isinstance(scenes, list):
        fail(
            f"{sample_id}: scenes is not a list"
        )

    print(
        f"PASS: {sample_id} — "
        f"{status} {score}/100 — "
        f"{len(dependencies)} dependencies — "
        f"{len(scenes)} scenes"
    )

    return {
        "status": status,
        "score": score,
        "dependencies": len(dependencies),
        "scenes": len(scenes),
    }


def check_scenario_diversity(results):
    statuses = {
        sample_id: result["status"]
        for sample_id, result in results.items()
    }

    # We expect the curated demos to demonstrate
    # meaningful decision variation.
    if len(set(statuses.values())) < 2:
        print(
            "WARNING: all curated scenarios returned "
            f"the same decision: {statuses}"
        )
    else:
        print(
            "PASS: curated scenarios demonstrate "
            f"decision variation: {statuses}"
        )


def main():
    print("=" * 70)
    print("GREENLIGHT — FINAL DEMO REGRESSION TEST")
    print("=" * 70)

    print("\n[1/4] FRONTEND CONTRACT")
    check_frontend_contract()

    print("\n[2/4] BACKEND CONTRACT")
    check_backend()

    print("\n[3/4] CURATED SCENARIO ANALYSIS")

    results = {}

    # Sort for deterministic test output.
    for sample_id in sorted(REQUIRED_SAMPLES):
        results[sample_id] = check_scenario(sample_id)

    print("\n[4/4] SCENARIO COVERAGE")
    check_scenario_diversity(results)

    print("\n" + "=" * 70)
    print("ALL REGRESSION SMOKE TESTS PASSED")
    print("=" * 70)

    print(
        "\nBrowser UAT still required:"
        "\n  1. Hard refresh"
        "\n  2. Analyze Brooklyn"
        "\n  3. Analyze Svalbard"
        "\n  4. Analyze Savannah"
        "\n  5. Switch back to Brooklyn"
        "\n  6. Switch back to Svalbard"
        "\n  7. Confirm each result persists"
        "\n  8. Click Reset Demo"
        "\n  9. Confirm everything clears"
        "\n 10. Run one scenario again"
    )


if __name__ == "__main__":
    main()