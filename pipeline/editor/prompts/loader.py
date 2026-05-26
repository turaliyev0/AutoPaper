"""Versioned prompt loader for the editor package."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_ROOT = Path(__file__).parent


def _load(name: str) -> str:
    path = _PROMPTS_ROOT / name / "current.md"
    if not path.is_file():
        raise FileNotFoundError(f"Editor prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_editor_orchestrator_instruction() -> str:
    return _load("openai_editor_orchestrator")


def load_section_writer_instruction() -> str:
    return _load("openai_section_writer")


def load_ieee_validator_instruction() -> str:
    return _load("gemini_ieee_validator")


def load_figure_generator_instruction() -> str:
    return _load("python_figure_generator")
