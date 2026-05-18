"""Application settings loaded from environment / .env (one section per agent)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="gpt-4o", validation_alias="RESEARCH_ORCHESTRATOR_MODEL"
    )

    # --- research / Gemini search agent ---
    research_gemini_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_GEMINI_SEARCH_API_KEY"
    )
    research_gemini_search_model: str = Field(
        default="gemini-2.0-flash", validation_alias="RESEARCH_GEMINI_SEARCH_MODEL"
    )

    # --- research / Claude search agent ---
    research_claude_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_CLAUDE_SEARCH_API_KEY"
    )
    research_claude_search_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        validation_alias="RESEARCH_CLAUDE_SEARCH_MODEL",
    )

    # --- research / Exa search agent ---
    research_exa_search_api_key: str = Field(
        default="", validation_alias="RESEARCH_EXA_SEARCH_API_KEY"
    )
    exa_api_key: str = Field(default="", validation_alias="EXA_API_KEY")
    exa_search_type: str = Field(default="deep", validation_alias="EXA_SEARCH_TYPE")
    exa_num_results: int = Field(default=10, validation_alias="EXA_NUM_RESULTS")

    # --- research / Report synthesizer (Claude) ---
    research_report_synthesizer_api_key: str = Field(
        default="", validation_alias="RESEARCH_REPORT_SYNTHESIZER_API_KEY"
    )
    research_report_synthesizer_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        validation_alias="RESEARCH_REPORT_SYNTHESIZER_MODEL",
    )

    # --- research / pipeline ---
    research_llm_max_retries: int = Field(default=3, validation_alias="RESEARCH_LLM_MAX_RETRIES")
    research_output_dir: Path = Field(
        default=Path("output/research_runs"),
        validation_alias="RESEARCH_OUTPUT_DIR",
    )

    # Legacy env names (optional fallbacks)
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
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

    @property
    def orchestrator_api_key(self) -> str:
        return (self.research_orchestrator_api_key or self.openai_api_key).strip()

    @property
    def orchestrator_model(self) -> str:
        return (self.research_orchestrator_model or "gpt-4o").strip()

    @property
    def gemini_search_api_key(self) -> str:
        return (
            self.research_gemini_search_api_key
            or self.research_gatherer_api_key
            or self.gemini_api_key
            or self.google_api_key
        ).strip()

    @property
    def gemini_search_model(self) -> str:
        return (
            self.research_gemini_search_model
            or self.research_gatherer_model
            or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        ).strip()

    @property
    def claude_search_api_key(self) -> str:
        return (
            self.research_claude_search_api_key
            or self.anthropic_api_key
            or os.environ.get("ANTHROPIC_API_KEY", "")
        ).strip()

    @property
    def claude_search_model(self) -> str:
        return (self.research_claude_search_model or "claude-3-5-sonnet-20241022").strip()

    @property
    def exa_search_api_key(self) -> str:
        return (self.research_exa_search_api_key or self.exa_api_key).strip()

    @property
    def report_synthesizer_api_key(self) -> str:
        return (
            self.research_report_synthesizer_api_key
            or self.research_analyst_api_key
            or self.anthropic_api_key
        ).strip()

    @property
    def report_synthesizer_model(self) -> str:
        return (
            self.research_report_synthesizer_model
            or self.research_analyst_model
            or "claude-3-5-sonnet-20241022"
        ).strip()

    def validate_keys(self) -> None:
        missing: list[str] = []
        if not self.orchestrator_api_key:
            missing.append("RESEARCH_ORCHESTRATOR_API_KEY (or OPENAI_API_KEY)")
        if not self.gemini_search_api_key:
            missing.append(
                "RESEARCH_GEMINI_SEARCH_API_KEY (or RESEARCH_GATHERER_API_KEY / GOOGLE_API_KEY)"
            )
        if not self.claude_search_api_key:
            missing.append(
                "RESEARCH_CLAUDE_SEARCH_API_KEY (or ANTHROPIC_API_KEY)"
            )
        if not self.exa_search_api_key:
            missing.append("RESEARCH_EXA_SEARCH_API_KEY (or EXA_API_KEY)")
        if not self.report_synthesizer_api_key:
            missing.append(
                "RESEARCH_REPORT_SYNTHESIZER_API_KEY (or RESEARCH_ANALYST_API_KEY)"
            )
        if missing:
            raise ValueError(f"Missing required API keys: {', '.join(missing)}")


def load_settings(env_path: Path | None = None) -> Settings:
    if env_path is not None:
        return Settings(_env_file=env_path)
    repo_env = Path(__file__).resolve().parent.parent / ".env"
    if repo_env.is_file():
        return Settings(_env_file=repo_env)
    return Settings()
