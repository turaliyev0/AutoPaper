"""Application settings loaded from environment / .env."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_GEMINI = "gemini-2.0-flash"
_DEFAULT_OPENAI = "gpt-4o"

# Search agents that actually run (claude_search and exa_search disabled for now).
ACTIVE_SEARCH_AGENT_IDS = frozenset({"gemini_search", "openai_search"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- research / Orchestrator (OpenAI GPT-4o) ---
    research_orchestrator_api_key: str = Field(
        default="", validation_alias="RESEARCH_ORCHESTRATOR_API_KEY"
    )
    research_orchestrator_model: str = Field(
        default=_DEFAULT_OPENAI, validation_alias="RESEARCH_ORCHESTRATOR_MODEL"
    )

    # --- research / gemini_search ---
    research_gemini_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_GEMINI_SEARCH_API_KEY"
    )
    research_gemini_search_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="RESEARCH_GEMINI_SEARCH_MODEL"
    )

    # --- research / openai_search ---
    research_openai_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_OPENAI_SEARCH_API_KEY"
    )
    research_openai_search_model: str = Field(
        default=_DEFAULT_OPENAI,
        validation_alias="RESEARCH_OPENAI_SEARCH_MODEL",
    )

    # --- research / claude_search (disabled) ---
    research_claude_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_CLAUDE_SEARCH_API_KEY"
    )
    research_claude_search_model: str = Field(
        default=_DEFAULT_GEMINI,
        validation_alias="RESEARCH_CLAUDE_SEARCH_MODEL",
    )

    # --- research / exa_search (disabled) ---
    research_exa_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_EXA_SEARCH_API_KEY"
    )
    research_exa_search_model: str = Field(
        default=_DEFAULT_GEMINI,
        validation_alias="RESEARCH_EXA_SEARCH_MODEL",
    )

    # --- research / Report synthesizer (Gemini) ---
    research_report_synthesizer_api_key: str = Field(
        default="", validation_alias="RESEARCH_REPORT_SYNTHESIZER_API_KEY"
    )
    research_report_synthesizer_model: str = Field(
        default=_DEFAULT_GEMINI,
        validation_alias="RESEARCH_REPORT_SYNTHESIZER_MODEL",
    )

    research_llm_max_retries: int = Field(default=3, validation_alias="RESEARCH_LLM_MAX_RETRIES")
    research_output_dir: Path = Field(
        default=Path("output/research_runs"),
        validation_alias="RESEARCH_OUTPUT_DIR",
    )

    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")

    research_gatherer_api_key: str = Field(
        default="", validation_alias="RESEARCH_GATHERER_API_KEY"
    )
    research_gatherer_model: str = Field(
        default="", validation_alias="RESEARCH_GATHERER_MODEL"
    )
    research_analyst_api_key: str = Field(
        default="", validation_alias="RESEARCH_ANALYST_API_KEY"
    )
    research_analyst_model: str = Field(
        default="", validation_alias="RESEARCH_ANALYST_MODEL"
    )

    @property
    def gemini_api_key_resolved(self) -> str:
        return (
            self.google_api_key
            or self.gemini_api_key
            or os.environ.get("GOOGLE_API_KEY", "")
            or os.environ.get("GEMINI_API_KEY", "")
        ).strip()

    @property
    def default_gemini_model(self) -> str:
        return (
            self.research_gemini_search_model
            or self.research_gatherer_model
            or os.environ.get("GEMINI_MODEL", _DEFAULT_GEMINI)
        ).strip()

    @property
    def orchestrator_api_key(self) -> str:
        return (self.research_orchestrator_api_key or self.openai_api_key).strip()

    @property
    def orchestrator_model(self) -> str:
        return (self.research_orchestrator_model or _DEFAULT_OPENAI).strip()

    @property
    def gemini_search_api_key(self) -> str:
        return (
            self.research_gemini_search_api_key
            or self.research_gatherer_api_key
            or self.gemini_api_key_resolved
        ).strip()

    @property
    def gemini_search_model(self) -> str:
        return (
            self.research_gemini_search_model
            or self.research_gatherer_model
            or self.default_gemini_model
        ).strip()

    @property
    def openai_search_api_key(self) -> str:
        return (self.research_openai_search_api_key or self.openai_api_key).strip()

    @property
    def openai_search_model(self) -> str:
        return (self.research_openai_search_model or _DEFAULT_OPENAI).strip()

    @property
    def report_synthesizer_api_key(self) -> str:
        return (
            self.research_report_synthesizer_api_key
            or self.research_analyst_api_key
            or self.gemini_api_key_resolved
        ).strip()

    @property
    def research_validator_api_key(self) -> str:
        return self.report_synthesizer_api_key

    @property
    def research_validator_model(self) -> str:
        return self.report_synthesizer_model

    @property
    def research_index_api_key(self) -> str:
        return self.report_synthesizer_api_key

    @property
    def research_index_model(self) -> str:
        return self.report_synthesizer_model

    @property
    def report_synthesizer_model(self) -> str:
        raw = (
            self.research_report_synthesizer_model
            or self.research_analyst_model
            or self.default_gemini_model
        ).strip()
        # Synthesizer uses Gemini API — Claude/Exa model ids from legacy .env must not pass through.
        lower = raw.lower()
        if lower.startswith("claude") or "anthropic" in lower:
            return self.default_gemini_model
        return raw

    def validate_keys(self, *, plan_only: bool = False) -> None:
        missing: list[str] = []
        if not self.orchestrator_api_key:
            missing.append("OPENAI_API_KEY")
        if plan_only:
            if missing:
                raise ValueError(f"Missing required API keys in .env: {', '.join(missing)}")
            return
        if not self.gemini_search_api_key:
            missing.append("GOOGLE_API_KEY")
        if not self.openai_search_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.report_synthesizer_api_key:
            missing.append("GOOGLE_API_KEY")
        if missing:
            seen: list[str] = []
            for name in missing:
                if name not in seen:
                    seen.append(name)
            raise ValueError(f"Missing required API keys in .env: {', '.join(seen)}")


def load_settings(env_path: Path | None = None) -> Settings:
    if env_path is not None:
        return Settings(_env_file=env_path)
    repo_env = Path(__file__).resolve().parent.parent / ".env"
    if repo_env.is_file():
        return Settings(_env_file=repo_env)
    return Settings()
