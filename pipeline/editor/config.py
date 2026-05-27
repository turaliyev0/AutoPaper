"""Editor settings — loaded from the same .env as the research package."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    pass

_DEFAULT_OPENAI = "gpt-4o"
_DEFAULT_GEMINI = "gemini-2.5-flash"


class EditorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- shared keys (same vars as research package) ---
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")

    # --- editor orchestrator (OpenAI) ---
    editor_orchestrator_model: str = Field(
        default=_DEFAULT_OPENAI, validation_alias="EDITOR_ORCHESTRATOR_MODEL"
    )

    # --- section writer (Gemini) ---
    editor_section_writer_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="EDITOR_SECTION_WRITER_MODEL"
    )

    # --- IEEE validator (Gemini) ---
    editor_validator_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="EDITOR_VALIDATOR_MODEL"
    )
    # Fall-back: read the same research-pipeline gemini model keys so that
    # a project .env with RESEARCH_GEMINI_SEARCH_MODEL or
    # RESEARCH_REPORT_SYNTHESIZER_MODEL is automatically honoured.
    research_gemini_search_model_fallback: str = Field(
        default="", validation_alias="RESEARCH_GEMINI_SEARCH_MODEL"
    )
    research_report_synthesizer_model_fallback: str = Field(
        default="", validation_alias="RESEARCH_REPORT_SYNTHESIZER_MODEL"
    )

    # --- figure generator (Gemini) ---
    editor_figure_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="EDITOR_FIGURE_MODEL"
    )

    # --- default IEEE format ---
    editor_ieee_format: str = Field(
        default="journal", validation_alias="EDITOR_IEEE_FORMAT"
    )

    editor_llm_max_retries: int = Field(
        default=6, validation_alias="EDITOR_LLM_MAX_RETRIES"
    )

    # max subprocess seconds for figure code execution
    editor_figure_exec_timeout: int = Field(
        default=120, validation_alias="EDITOR_FIGURE_EXEC_TIMEOUT"
    )
    editor_figure_max_retries: int = Field(
        default=3, validation_alias="EDITOR_FIGURE_MAX_RETRIES"
    )

    @property
    def openai_key(self) -> str:
        return self.openai_api_key.strip()

    @property
    def gemini_key(self) -> str:
        return (self.google_api_key or self.gemini_api_key).strip()

    # --- compatibility shims so research.clients.OpenAIClient + GeminiClient accept EditorSettings ---
    @property
    def orchestrator_api_key(self) -> str:
        return self.openai_key

    @property
    def orchestrator_model(self) -> str:
        return self.editor_orchestrator_model

    @property
    def gemini_search_api_key(self) -> str:
        return self.gemini_key

    @property
    def default_gemini_model(self) -> str:
        return (
            self.editor_validator_model
            or self.research_gemini_search_model_fallback
            or self.research_report_synthesizer_model_fallback
            or _DEFAULT_GEMINI
        )

    @staticmethod
    def _coerce_gemini_model(raw: str, *, fallback: str) -> str:
        lower = raw.strip().lower()
        if lower.startswith("gpt") or lower.startswith("o1") or lower.startswith("o3"):
            return fallback
        return raw.strip() or fallback

    @property
    def section_writer_model(self) -> str:
        return self._coerce_gemini_model(
            self.editor_section_writer_model,
            fallback=self.default_gemini_model,
        )

    @property
    def figure_model(self) -> str:
        return self._coerce_gemini_model(
            self.editor_figure_model,
            fallback=self.default_gemini_model,
        )

    def validate_keys(self) -> None:
        missing: list[str] = []
        if not self.openai_key:
            missing.append("OPENAI_API_KEY")
        if not self.gemini_key:
            missing.append("GOOGLE_API_KEY")
        if missing:
            raise ValueError(f"Editor: missing required API keys in .env: {', '.join(missing)}")


def load_editor_settings(env_path: Path | None = None) -> EditorSettings:
    if env_path is not None:
        return EditorSettings(_env_file=env_path)
    repo_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if repo_env.is_file():
        return EditorSettings(_env_file=repo_env)
    return EditorSettings()
