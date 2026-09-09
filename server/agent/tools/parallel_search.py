"""Production Parallel Search API integration for Google ADK.

Adheres strictly to security, reliability, and architectural requirements:
- Reads configuration exclusively from server.config.settings.
- Authenticates using the required x-api-key header.
- Never logs, prints, or exposes the API key in responses, errors, or telemetry.
- Validates responses against ParallelSearchResponse / SearchSource models.
- Distinguishes live Parallel results (is_mock=False) from demo fallbacks (is_mock=True).
- Ready for registration as a Google ADK FunctionTool.
"""

from typing import Any, Dict, List, Optional
import httpx
from pydantic import ValidationError

from server.config import settings
from server.models.research import (
    ParallelSearchResponse,
    ResearchConfidence,
    ResearchResult,
    SearchSource,
)
from server.services.sample_library import get_fallback_research


async def search_parallel(
    objective: str,
    search_queries: List[str],
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> ResearchResult:
    """Performs an authenticated external search via Parallel Search API.

    Args:
        objective: The high-level investigative goal of the search.
        search_queries: High-precision search query strings.
        client: Optional httpx.AsyncClient for dependency injection (e.g. testing).

    Returns:
        Typed ResearchResult containing verified sources, findings, and metadata.
    """
    # 1. Check if Parallel API key is configured
    if not settings.is_parallel_configured:
        if settings.demo_mode:
            fallback = get_fallback_research(objective)
            if fallback:
                sources = [
                    SearchSource(
                        title=item.title,
                        url=item.url,
                        publish_date=item.publish_date,
                        excerpts=item.excerpts,
                        relevance_score=0.95,
                    )
                    for item in fallback.results
                ]
                findings = [
                    f"{s.title}: {s.excerpts[0]}"
                    for s in sources
                    if s.excerpts
                ]
                return ResearchResult(
                    search_id=fallback.search_id,
                    objective=objective,
                    sources=sources,
                    key_findings=findings,
                    confidence=ResearchConfidence.MEDIUM,
                    is_mock=True,
                    error="PARALLEL_API_KEY is not configured in environment settings",
                )

        return ResearchResult(
            objective=objective,
            sources=[],
            key_findings=[],
            confidence=ResearchConfidence.LOW,
            is_mock=True,
            error="PARALLEL_API_KEY is not configured in environment settings",
        )

    # 2. Build authenticated request payload
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.parallel_api_key,
    }
    # Limit queries to top 3 focused items to respect search latency budget
    clean_queries = [q.strip() for q in search_queries if q and q.strip()][:3]
    if not clean_queries:
        clean_queries = [objective.strip()]

    payload = {
        "objective": objective,
        "search_queries": clean_queries,
    }

    # 3. Execute request with async HTTP client
    should_close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
        should_close_client = True

    try:
        response = await client.post(
            settings.parallel_api_url,
            json=payload,
            headers=headers,
        )

        if response.status_code != 200:
            # Safe status diagnosis without exposing sensitive request headers
            error_msg = f"Parallel Search API returned HTTP {response.status_code}"
            try:
                err_json = response.json()
                if "error" in err_json:
                    detail = err_json.get("error", {}).get("message") or err_json.get("message")
                    if detail:
                        error_msg = f"Parallel API error ({response.status_code}): {detail}"
            except Exception:
                pass

            # Fallback if in demo mode
            if settings.demo_mode:
                fallback = get_fallback_research(objective)
                if fallback:
                    sources = [
                        SearchSource(
                            title=item.title,
                            url=item.url,
                            publish_date=item.publish_date,
                            excerpts=item.excerpts,
                            relevance_score=0.90,
                        )
                        for item in fallback.results
                    ]
                    return ResearchResult(
                        search_id=fallback.search_id,
                        objective=objective,
                        sources=sources,
                        key_findings=[s.excerpts[0] for s in sources if s.excerpts],
                        confidence=ResearchConfidence.MEDIUM,
                        is_mock=True,
                        error=error_msg,
                    )

            return ResearchResult(
                objective=objective,
                sources=[],
                key_findings=[],
                confidence=ResearchConfidence.LOW,
                is_mock=False,
                error=error_msg,
            )

        # 4. Parse and validate response
        raw_data = response.json()
        if not isinstance(raw_data, dict) or "results" not in raw_data or not isinstance(raw_data.get("results"), list):
            raise ValueError("Missing or malformed 'results' array in Parallel Search response")
        validated_resp = ParallelSearchResponse.model_validate(raw_data)

        # 5. Map to typed domain models
        sources: List[SearchSource] = [
            SearchSource(
                title=item.title,
                url=item.url,
                publish_date=item.publish_date,
                excerpts=item.excerpts,
                relevance_score=1.0 - (idx * 0.05),
            )
            for idx, item in enumerate(validated_resp.results)
        ]

        key_findings = []
        for s in sources[:4]:
            if s.excerpts:
                key_findings.append(f"[{s.title}]: {s.excerpts[0]}")

        return ResearchResult(
            search_id=validated_resp.search_id,
            objective=objective,
            sources=sources,
            key_findings=key_findings,
            confidence=ResearchConfidence.HIGH,
            is_mock=False,
            error=None,
        )

    except httpx.TimeoutException:
        return ResearchResult(
            objective=objective,
            sources=[],
            key_findings=[],
            confidence=ResearchConfidence.LOW,
            is_mock=False,
            error="Parallel Search API request timed out (30s threshold exceeded)",
        )
    except httpx.RequestError as exc:
        return ResearchResult(
            objective=objective,
            sources=[],
            key_findings=[],
            confidence=ResearchConfidence.LOW,
            is_mock=False,
            error=f"Parallel Search network connection error: {type(exc).__name__}",
        )
    except ValueError as exc:
        return ResearchResult(
            objective=objective,
            sources=[],
            key_findings=[],
            confidence=ResearchConfidence.LOW,
            is_mock=False,
            error=f"Malformed response schema from Parallel Search API: {str(exc)[:120]}",
        )
    except ValidationError as exc:
        return ResearchResult(
            objective=objective,
            sources=[],
            key_findings=[],
            confidence=ResearchConfidence.LOW,
            is_mock=False,
            error=f"Malformed response schema from Parallel Search API: {str(exc)[:120]}",
        )
    finally:
        if should_close_client:
            await client.aclose()


async def parallel_search(objective: str, search_queries: List[str]) -> Dict[str, Any]:
    """ADK Tool: Searches live web intelligence using the Parallel Search API.

    Inspects real-world municipal film commission rules, FAA aviation waivers,
    union regulations, safety codes, and environmental/weather constraints.

    Args:
        objective: Core investigative goal (e.g. 'Verify NYC drone filming permit rules').
        search_queries: Up to 3 high-precision search query strings.

    Returns:
        Structured dictionary containing research findings, verified source URLs, and excerpts.
    """
    result = await search_parallel(objective, search_queries)
    return result.model_dump()
