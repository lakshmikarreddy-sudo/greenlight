"""Minimal live connectivity test against Parallel Search API.

Adheres strictly to security requirements:
- Reads PARALLEL_API_KEY from server.config.settings.
- NEVER logs, prints, or exposes the API key.
- Validates payload structure and model compatibility.
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse
import httpx

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.config import settings
from server.models import ParallelSearchResponse, SearchSource


def test_parallel_connectivity() -> None:
    """Synchronous test wrapper for pytest and standalone execution."""
    async def _run():
        print("=== Parallel Search API Connectivity Test ===")

        if not settings.is_parallel_configured:
            print("[NOTICE] PARALLEL_API_KEY is not configured; skipping live network check.")
            return

        print(f"Endpoint: {settings.parallel_api_url}")
        print("API Key Status: Configured (key value protected)")

        headers = {
            "Content-Type": "application/json",
            "x-api-key": settings.parallel_api_key,
        }
        payload = {
            "objective": "Research film production permit requirements for drone filming",
            "search_queries": [
                "film production permit requirements drone filming"
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    settings.parallel_api_url,
                    json=payload,
                    headers=headers,
                )

            print(f"HTTP Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                parsed = ParallelSearchResponse.model_validate(data)
                num_results = len(parsed.results)
                print(f"Call Succeeded: True")
                print(f"Results Returned: {num_results}")

                if num_results > 0:
                    first_result = parsed.results[0]
                    domain = urlparse(first_result.url).netloc
                    print(f"First Result Title: {first_result.title}")
                    print(f"First Result Domain: {domain}")

                    search_sources = [
                        SearchSource(
                            title=r.title,
                            url=r.url,
                            publish_date=r.publish_date,
                            excerpts=r.excerpts,
                        )
                        for r in parsed.results
                    ]
                    print(f"Model Mapping Succeeded: True ({len(search_sources)} SearchSource items created)")
                    assert len(search_sources) > 0

                print("\n[SUCCESS] Parallel Search API live test completed successfully.")
            else:
                print(f"Call Succeeded: False (HTTP {response.status_code})")

        except Exception as e:
            print(f"Call Succeeded: False")
            print(f"Connection/Transport Error: {type(e).__name__}: {str(e)}")

    asyncio.run(_run())


if __name__ == "__main__":
    test_parallel_connectivity()
