"""Load versioned prompts from ``research/prompts/<family>/current.md``."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_ROOT = Path(__file__).resolve().parent


def prompts_root() -> Path:
    return _PROMPTS_ROOT


def _load_family_prompt(family: str) -> str:
    path = _PROMPTS_ROOT / family / "current.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing system prompt: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_orchestrator_instruction() -> str:
    """OpenAI orchestrator (GPT-4o): plan via function calling."""
    return _load_family_prompt("openai_orchestrator")


def load_gemini_search_instruction() -> str:
    """Gemini search agent: one subtask → structured JSON."""
    return _load_family_prompt("gemini_search")


def load_openai_search_instruction() -> str:
    """OpenAI search agent: one subtask → structured JSON."""
    return _load_family_prompt("openai_search")


def load_report_synthesizer_instruction() -> str:
    """Legacy alias — research index catalog."""
    return load_research_index_instruction()


def load_research_validator_instruction() -> str:
    """Gemini research validator: per-task source and clarity."""
    return _load_family_prompt("gemini_research_validator")


def load_research_index_instruction() -> str:
    """Gemini research index: final catalog Markdown."""
    return _load_family_prompt("gemini_research_index")


def list_prompt_archive_versions(family: str) -> list[str]:
    archive = _PROMPTS_ROOT / family / "archive"
    if not archive.is_dir():
        return []
    return sorted(p.name for p in archive.glob("v*.md"))
