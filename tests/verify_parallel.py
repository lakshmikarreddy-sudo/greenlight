"""Standalone verification script for the live Parallel Search API integration.

Executes exactly ONE authenticated search query using the configured Parallel API key.
Adheres strictly to security requirements:
- Never prints, logs, or exposes the API key.
- Validates model mapping into ResearchResult and SearchSource.
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.config import settings
from server.agent.tools.parallel_search import search_parallel
from server.models.research import ResearchResult, SearchSource


async def verify_live_parallel() -> None:
    print("=== Greenlight: Parallel Search API Live Verification ===")

    if not settings.is_parallel_configured:
        print("[FAIL] PARALLEL_API_KEY is not configured in settings.")
        sys.exit(1)

    print(f"Target Endpoint : {settings.parallel_api_url}")
    print("API Key Status  : Loaded & Protected (never printed)")

    objective = "Verify FAA Part 107 waiver and NYC permits for drone filming at night"
    queries = [
        "film production permit requirements drone filming night FAA",
        "NYC Mayor Office Media Entertainment drone guidelines",
    ]

    print(f"Objective       : {objective}")
    print("Executing live request...")

    result: ResearchResult = await search_parallel(
        objective=objective,
        search_queries=queries,
    )

    success = (result.error is None) and (len(result.sources) > 0)
    print(f"\nExecution Status : {'SUCCESS' if success else 'FAILED'}")
    print(f"HTTP Error       : {result.error if result.error else 'None (200 OK)'}")
    print(f"Results Count    : {len(result.sources)}")
    print(f"Is Mock Fallback : {result.is_mock}")
    print(f"Confidence Level : {result.confidence.value}")

    if result.sources:
        first = result.sources[0]
        domain = urlparse(first.url).netloc
        print(f"First Title      : {first.title}")
        print(f"First Domain     : {domain}")
        print(f"Model Validated  : True ({type(first).__name__} instances created)")
        if first.excerpts:
            print(f"Sample Excerpt   : {first.excerpts[0][:120]}...")
    else:
        print("First Result     : None")
        print("Model Validated  : False (No sources returned)")

    print("\n=======================================================")
    if success:
        print("PARALLEL SEARCH TOOL VERIFICATION COMPLETE: [PASS]")
    else:
        print("PARALLEL SEARCH TOOL VERIFICATION COMPLETE: [FAIL]")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(verify_live_parallel())
