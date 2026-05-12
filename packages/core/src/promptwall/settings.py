"""Environment-driven configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime knobs sourced from the environment.

    Most names are prefixed with ``PROMPTWALL_`` to stay out of other tools'
    way. ``OPENAI_API_KEY`` is accepted unprefixed because that's the
    convention every OpenAI-aware tool already uses.
    """

    model_config = SettingsConfigDict(
        env_prefix="PROMPTWALL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://promptwall:promptwall@localhost:5432/promptwall"

    openai_api_key: str = Field(
        validation_alias=AliasChoices("PROMPTWALL_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = 60.0

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "promptwall"

    log_level: str = "INFO"
    log_renderer: str = "json"

    policy_path: Path = Path("policies/default.yaml")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide singleton; reads env exactly once."""
    return Settings()
