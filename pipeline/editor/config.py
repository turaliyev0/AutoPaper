"""Editor settings — loaded from the same .env as the research package."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_OPENAI = "gpt-4o"
_DEFAULT_GEMINI = "gemini-2.5-flash"
_DEFAULT_CLAUDE = "claude-sonnet-4-6"


class EditorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

    editor_orchestrator_model: str = Field(
        default=_DEFAULT_OPENAI, validation_alias="EDITOR_ORCHESTRATOR_MODEL"
    )
    editor_section_writer_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="EDITOR_SECTION_WRITER_MODEL"
    )
    editor_manuscript_qa_model: str = Field(
        default=_DEFAULT_CLAUDE, validation_alias="EDITOR_MANUSCRIPT_QA_MODEL"
    )
    editor_figure_model: str = Field(
        default=_DEFAULT_GEMINI, validation_alias="EDITOR_FIGURE_MODEL"
    )
    editor_ieee_format: str = Field(
        default="journal", validation_alias="EDITOR_IEEE_FORMAT"
    )

    editor_llm_max_retries: int = Field(
        default=6, validation_alias="EDITOR_LLM_MAX_RETRIES"
    )
    editor_figure_exec_timeout: int = Field(
        default=120, validation_alias="EDITOR_FIGURE_EXEC_TIMEOUT"
    )
    editor_figure_max_retries: int = Field(
        default=3, validation_alias="EDITOR_FIGURE_MAX_RETRIES"
    )
    editor_qa_score_threshold: int = Field(
        default=70,
        validation_alias="EDITOR_QA_SCORE_THRESHOLD",
        description="Manuscript QA score below this triggers section rewrites.",
    )
    editor_qa_max_rounds: int = Field(
        default=3,
        validation_alias="EDITOR_QA_MAX_ROUNDS",
        description="Holistic manuscript QA revision rounds (figures + sections together).",
    )

    @property
    def openai_key(self) -> str:
        return self.openai_api_key.strip()

    @property
    def gemini_key(self) -> str:
        return self.google_api_key.strip()

    @property
    def orchestrator_api_key(self) -> str:
        return self.openai_key

    @property
    def orchestrator_model(self) -> str:
        return self.editor_orchestrator_model.strip()

    @property
    def gemini_search_api_key(self) -> str:
        return self.gemini_key

    @property
    def section_writer_model(self) -> str:
        return self.editor_section_writer_model.strip()

    @property
    def figure_model(self) -> str:
        return self.editor_figure_model.strip()

    @property
    def manuscript_qa_model(self) -> str:
        return self.editor_manuscript_qa_model.strip()

    @property
    def manuscript_qa_api_key(self) -> str:
        return self.anthropic_api_key.strip()

    def validate_keys(self) -> None:
        missing: list[str] = []
        if not self.openai_key:
            missing.append("OPENAI_API_KEY")
        if not self.gemini_key:
            missing.append("GOOGLE_API_KEY")
        if not self.anthropic_api_key.strip():
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            raise ValueError(f"Editor: missing required API keys in .env: {', '.join(missing)}")


def load_editor_settings(env_path: Path | None = None) -> EditorSettings:
    if env_path is not None:
        return EditorSettings(_env_file=env_path)
    repo_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if repo_env.is_file():
        return EditorSettings(_env_file=repo_env)
    return EditorSettings()
