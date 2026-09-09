"""Minimal Google ADK Agent configured for Google Cloud Vertex AI."""

from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    name="greenlight_agent",
    model="gemini-2.5-flash",
    description="Minimal Google ADK agent solely to verify Vertex AI Gemini invocation.",
    instruction="You are a minimal Google ADK assistant. Keep your responses concise.",
)
