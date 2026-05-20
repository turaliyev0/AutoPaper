"""Load versioned prompts from ``paper_input/prompts/<family>/current.md``."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_ROOT = Path(__file__).resolve().parent


def prompts_root() -> Path:
    """Root directory of the ``paper_input.prompts`` package (contains per-family folders)."""
    return _PROMPTS_ROOT


def _load_family_prompt(family: str) -> str:
    path = _PROMPTS_ROOT / family / "current.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing system prompt: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_text_parser_instruction() -> str:
    """Text Parser Agent (step 1): text and metadata only."""
    return _load_family_prompt("gemini_text_parser")


def load_vision_instruction() -> str:
    """Vision Agent (step 2): images only."""
    return _load_family_prompt("gemini_image_description")


def load_joiner_instruction() -> str:
    """Joiner Agent (step 3): combine cleaned text + cleaned images."""
    return _load_family_prompt("gemini_joiner")


