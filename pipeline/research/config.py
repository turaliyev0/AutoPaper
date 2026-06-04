"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_GEMINI = "gemini-2.5-flash"
_DEFAULT_OPENAI = "gpt-4o"
_DEFAULT_CLAUDE = "claude-sonnet-4-6"

ACTIVE_SEARCH_AGENT_IDS = frozenset({"gemini_search", "openai_search"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

    research_orchestrator_model: str = Field(
        default=_DEFAULT_OPENAI, validation_alias="RESEARCH_ORCHESTRATOR_MODEL"
    )
    research_gemini_search_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="RESEARCH_GEMINI_SEARCH_MODEL"
    )
    research_openai_search_model: str = Field(
        default=_DEFAULT_GEMINI,
        validation_alias="RESEARCH_OPENAI_SEARCH_MODEL",
    )
    research_index_model: str = Field(
        default=_DEFAULT_GEMINI,
        validation_alias="RESEARCH_INDEX_MODEL",
    )
    research_validator_model: str = Field(
        default=_DEFAULT_CLAUDE,
        validation_alias="RESEARCH_VALIDATOR_MODEL",
    )

    research_llm_max_retries: int = Field(default=8, validation_alias="RESEARCH_LLM_MAX_RETRIES")
    research_gemini_max_concurrent: int = Field(
        default=2,
        validation_alias="RESEARCH_GEMINI_MAX_CONCURRENT",
        description="Max parallel Gemini search calls (reduces 503 spikes).",
    )
    research_output_dir: Path = Field(
        default=Path("output/research_runs"),
        validation_alias="RESEARCH_OUTPUT_DIR",
    )
    research_followup_rounds: int = Field(
        default=1, validation_alias="RESEARCH_FOLLOWUP_ROUNDS"
    )
    research_followup_max_tasks: int = Field(
        default=4, validation_alias="RESEARCH_FOLLOWUP_MAX_TASKS"
    )

    @property
    def orchestrator_api_key(self) -> str:
        return self.openai_api_key.strip()

    @property
    def orchestrator_model(self) -> str:
        return self.research_orchestrator_model.strip()

    @property
    def gemini_search_api_key(self) -> str:
        return self.google_api_key.strip()

    @property
    def gemini_search_model(self) -> str:
        return self.research_gemini_search_model.strip()

    @property
    def openai_search_api_key(self) -> str:
        return self.google_api_key.strip()

    @property
    def openai_search_model(self) -> str:
        return self.research_openai_search_model.strip()

    @property
    def research_index_api_key(self) -> str:
        return self.google_api_key.strip()

    @property
    def research_validator_api_key(self) -> str:
        return self.anthropic_api_key.strip()

    def validate_keys(self, *, plan_only: bool = False) -> None:
        missing: list[str] = []
        if not self.openai_api_key.strip():
            missing.append("OPENAI_API_KEY")
        if plan_only:
            if missing:
                raise ValueError(f"Missing required API keys in .env: {', '.join(missing)}")
            return
        if not self.google_api_key.strip():
            missing.append("GOOGLE_API_KEY")
        if not self.anthropic_api_key.strip():
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            raise ValueError(f"Missing required API keys in .env: {', '.join(missing)}")


def load_settings(env_path: Path | None = None) -> Settings:
    if env_path is not None:
        return Settings(_env_file=env_path)
    repo_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if repo_env.is_file():
        return Settings(_env_file=repo_env)
    return Settings()
