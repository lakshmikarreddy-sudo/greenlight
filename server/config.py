"""Centralized application settings for Greenlight."""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate root directory containing .env
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and root .env file."""

    model_config = SettingsConfigDict(
        env_file=(
            str(ROOT_DIR / ".env"),
            str(ROOT_DIR / "greenlight_agent" / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application Metadata
    app_name: str = "Greenlight"
    app_description: str = "AI Production-Intelligence Agent for Cinema"
    app_version: str = "0.1.0"
    debug: bool = False

    # Google Cloud / Vertex AI Settings
    google_cloud_project: str = Field(
        default="greenlight-ac-2026-lkr",
        description="Google Cloud project ID for Vertex AI",
    )
    google_cloud_location: str = Field(
        default="us-central1",
        description="Google Cloud compute region for Vertex AI",
    )
    google_genai_use_vertexai: bool = Field(
        default=True,
        description="Whether google-genai and ADK use Vertex AI backend instead of AI Studio",
    )
    model_name: str = Field(
        default="gemini-2.5-flash",
        description="Default Gemini foundation model identifier",
    )

    # Parallel Search API Settings
    parallel_api_key: Optional[str] = Field(
        default=None,
        description="API Key for Parallel Search API (platform.parallel.ai). Optional for demo mode.",
    )
    parallel_api_url: str = Field(
        default="https://api.parallel.ai/v1/search",
        description="Parallel Search API endpoint",
    )

    # Demo & Resilience Settings
    demo_mode: bool = Field(
        default=False,
        description="If True, enables local high-fidelity demonstration fallback when GCP billing or Parallel keys are inactive",
    )

    @property
    def is_parallel_configured(self) -> bool:
        """Returns True if a non-empty Parallel API key is present."""
        return bool(self.parallel_api_key and self.parallel_api_key.strip())

    @property
    def is_vertex_configured(self) -> bool:
        """Returns True if Google Cloud Project is set."""
        return bool(self.google_cloud_project and self.google_cloud_project.strip())


import os

# Single global settings instance for the entire application
settings = Settings()

# Synchronize Vertex AI settings with os.environ for google.genai and google.adk
if settings.google_genai_use_vertexai:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
if settings.google_cloud_project:
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
if settings.google_cloud_location:
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
