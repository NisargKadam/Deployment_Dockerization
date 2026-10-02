"""Typed environment configuration, validated when the application imports."""

import os
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PORT = int(os.environ.get("PORT", 8000))


class Settings(BaseSettings):
    """Runtime settings loaded from the environment and an optional local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "humanizer-agent"
    app_mode: Literal["live", "demo"] = "live"
    enable_demo_scenarios: bool = False
    class_access_token: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "deployments-observability"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_workspace_id: str = ""
    langsmith_hide_inputs: bool = False
    langsmith_hide_outputs: bool = False
    environment: Literal["local", "docker", "railway", "azure", "aws", "test", "production"] = (
        "local"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    port: int = Field(default=PORT, ge=1, le=65535)
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1)
    max_input_chars: int = Field(default=12_000, ge=1)
    max_passes: int = Field(default=3, ge=1, le=3)
    score_threshold: float = Field(default=85.0, ge=0, le=100)
    request_timeout_seconds: float = Field(default=120, gt=0)
    max_tokens_per_request: int = Field(default=8_000, ge=1)
    storage_backend: Literal["local", "s3", "azure"] = "local"
    enable_mcp: bool = False
    postgres_url: str | None = None


settings = Settings()
