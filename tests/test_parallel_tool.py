"""Unit and integration tests for the Parallel Search tool."""

import asyncio
import json
from typing import Any, Dict
import httpx
import pytest

from server.config import Settings, settings
from server.agent.tools.parallel_search import parallel_search, search_parallel
from server.models.research import ResearchConfidence, ResearchResult


# ------------------------------------------------------------------------------
# Test 1: Successful Response Validation (Mocked)
# ------------------------------------------------------------------------------
def test_parallel_search_success_mocked(monkeypatch):
    """Verifies that a valid 200 response from Parallel is parsed into typed ResearchResult."""
    mock_response_data = {
        "search_id": "par_test_12345",
        "results": [
            {
                "url": "https://www.nyc.gov/site/mome/permits/uas-guidelines.page",
                "title": "NYC UAS Filming Guidelines",
                "publish_date": "2024-01-10",
                "excerpts": ["Applications for drone filming must be submitted at least 30 business days prior."],
            }
        ],
        "session_id": "sess_123",
    }

    async def _test():
        async def mock_handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("x-api-key") is not None
            assert "objective" in json.loads(request.content)
            return httpx.Response(200, json=mock_response_data)

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await search_parallel(
                objective="Verify NYC drone filming permit rules",
                search_queries=["NYC drone filming permit requirements"],
                client=client,
            )

        assert isinstance(result, ResearchResult)
        assert result.search_id == "par_test_12345"
        assert result.is_mock is False
        assert result.confidence == ResearchConfidence.HIGH
        assert len(result.sources) == 1
        assert result.sources[0].url == "https://www.nyc.gov/site/mome/permits/uas-guidelines.page"
        assert result.sources[0].title == "NYC UAS Filming Guidelines"
        assert len(result.key_findings) > 0

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 2: API Key is Never Included in Output or Returned Data
# ------------------------------------------------------------------------------
def test_api_key_not_exposed_in_result(monkeypatch):
    """Ensures that the API key is never leaked in result objects, JSON dumps, or strings."""
    secret_key = "SECRET_SUPER_SENSITIVE_KEY_12345"
    monkeypatch.setattr(settings, "parallel_api_key", secret_key)

    mock_response_data = {
        "search_id": "par_test_secret",
        "results": [{"url": "https://example.com", "title": "Example", "excerpts": ["Safe content"]}],
    }

    async def _test():
        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=mock_response_data)

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await search_parallel(
                objective="Security check",
                search_queries=["security check"],
                client=client,
            )

        dumped_dict = result.model_dump()
        dumped_json = result.model_dump_json()
        string_repr = str(result)

        assert secret_key not in dumped_json
        assert secret_key not in string_repr
        assert secret_key not in str(dumped_dict)

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 3: Missing API Key Behavior (Without Demo Mode)
# ------------------------------------------------------------------------------
def test_missing_api_key_behavior(monkeypatch):
    """Verifies graceful behavior when PARALLEL_API_KEY is not configured and demo_mode is False."""
    monkeypatch.setattr(settings, "parallel_api_key", None)
    monkeypatch.setattr(settings, "demo_mode", False)

    async def _test():
        result = await search_parallel(
            objective="Verify drone permits",
            search_queries=["drone permits"],
        )

        assert isinstance(result, ResearchResult)
        assert result.is_mock is True
        assert result.confidence == ResearchConfidence.LOW
        assert "PARALLEL_API_KEY is not configured" in (result.error or "")

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 4: Demo Fallback Behavior (When Key Missing & Demo Mode Active)
# ------------------------------------------------------------------------------
def test_demo_fallback_behavior(monkeypatch):
    """Verifies that demo_mode=True serves high-fidelity demo fixtures marked is_mock=True."""
    monkeypatch.setattr(settings, "parallel_api_key", None)
    monkeypatch.setattr(settings, "demo_mode", True)

    async def _test():
        result = await search_parallel(
            objective="Verify NYC drone filming permit rules for Brooklyn Bridge",
            search_queries=["NYC drone permit Brooklyn Bridge"],
        )

        assert isinstance(result, ResearchResult)
        assert result.is_mock is True
        assert result.confidence == ResearchConfidence.MEDIUM
        assert len(result.sources) > 0
        assert "nyc.gov" in result.sources[0].url.lower()

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 5: HTTP Status / API Failure Handling
# ------------------------------------------------------------------------------
def test_http_error_handling(monkeypatch):
    """Verifies non-crashing, safe error handling on 401, 403, and 500 status codes."""
    monkeypatch.setattr(settings, "demo_mode", False)

    async def _test():
        for status_code in [401, 403, 500]:
            async def mock_error_handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(status_code, json={"error": {"message": "Invalid authentication"}})

            transport = httpx.MockTransport(mock_error_handler)
            async with httpx.AsyncClient(transport=transport) as client:
                result = await search_parallel(
                    objective="Error test",
                    search_queries=["query"],
                    client=client,
                )

            assert isinstance(result, ResearchResult)
            assert result.confidence == ResearchConfidence.LOW
            assert str(status_code) in (result.error or "")

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 6: Network Timeout Handling
# ------------------------------------------------------------------------------
def test_timeout_handling():
    """Verifies graceful handling of client timeouts."""
    async def _test():
        async def mock_timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Timeout exceeded")

        transport = httpx.MockTransport(mock_timeout_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await search_parallel(
                objective="Timeout test",
                search_queries=["query"],
                client=client,
            )

        assert isinstance(result, ResearchResult)
        assert "timed out" in (result.error or "").lower()

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 7: Malformed API Response Handling
# ------------------------------------------------------------------------------
def test_malformed_response_handling():
    """Verifies handling when the API returns unexpected non-schema data."""
    async def _test():
        async def mock_malformed_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected_format": 12345})

        transport = httpx.MockTransport(mock_malformed_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await search_parallel(
                objective="Malformed test",
                search_queries=["query"],
                client=client,
            )

        assert isinstance(result, ResearchResult)
        # Results should be empty or handle cleanly
        assert result.error is None or "Malformed" in result.error

    asyncio.run(_test())


# ------------------------------------------------------------------------------
# Test 8: ADK FunctionTool Compatibility (Dict return)
# ------------------------------------------------------------------------------
def test_adk_tool_dictionary_serialization():
    """Verifies parallel_search entrypoint returns a valid dictionary for ADK FunctionTool."""
    async def _test():
        dict_result = await parallel_search(
            objective="Verify drone permits",
            search_queries=["drone permits"],
        )
        assert isinstance(dict_result, dict)
        assert "objective" in dict_result
        assert "sources" in dict_result
        assert "confidence" in dict_result

    asyncio.run(_test())
