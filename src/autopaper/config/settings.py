from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTOPAPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, description="OpenAI API key for GPT")
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key for Claude")
    google_api_key: str | None = Field(default=None, description="Google AI API key for Gemini")

    default_model_gpt: str = "gpt-4o-mini"
    default_model_claude: str = "claude-3-5-sonnet-20241022"
    default_model_gemini: str = "gemini-1.5-pro"
