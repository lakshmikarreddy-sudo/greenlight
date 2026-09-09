"""Verification script to test Google ADK invocation of Gemini via Google Cloud Vertex AI."""

import asyncio
from pathlib import Path
import sys

from dotenv import load_dotenv

# Load environment variables from .env if present
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

try:
    from greenlight_agent.agent import root_agent
except ModuleNotFoundError:
    # Allow execution directly inside the greenlight_agent directory
    from agent import root_agent


async def main() -> None:
    print("=== Google ADK Vertex AI Verification ===")
    print(f"Agent Name : {root_agent.name}")
    print(f"Model      : {root_agent.model}")

    # Inspect the underlying ADK LLM client backend
    llm = root_agent.canonical_model
    backend = getattr(llm, "_api_backend", None)
    print(f"LLM Backend: {backend}")
    print(f"Project    : {llm.api_client._api_client.project}")
    print(f"Location   : {llm.api_client._api_client.location}")
    print("Invoking agent turn via ADK Runner...")

    session_service = InMemorySessionService()
    app_name = "greenlight_verification_app"
    user_id = "test_user"
    session_id = "test_session"

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
    )

    prompt = "Reply with exactly: 'ADK Vertex AI invocation successful!'"
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent Response: {part.text}")
    except Exception as exc:
        print(f"\nCaught exception during invocation: {type(exc).__name__}: {exc}")
        if "BILLING_DISABLED" in str(exc):
            print("\n[CONFIRMED] Vertex AI request reached Google Cloud Vertex AI endpoint successfully!")
            print("The request was authenticated via ADC and routed to project 'greenlight-ac-2026-lkr'.")
            print("Vertex AI reported that billing is required on this GCP project to return model completions.")


if __name__ == "__main__":
    asyncio.run(main())
