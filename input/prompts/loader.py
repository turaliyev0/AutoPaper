"""Load versioned prompts from ``input/prompts/<family>/current.md``."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_ROOT = Path(__file__).resolve().parent


def prompts_root() -> Path:
    """Root directory of the ``input.prompts`` package (contains per-family folders)."""
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


def load_gemini_flash_system_instruction() -> str:
    """Deprecated alias for joiner prompt (use :func:`load_joiner_instruction`)."""
    return load_joiner_instruction()


def load_gemini_image_description_instruction() -> str:
    """Deprecated alias for vision prompt (use :func:`load_vision_instruction`)."""
    return load_vision_instruction()


def list_gemini_flash_system_archive_versions() -> list[str]:
    """Sorted archive filenames under ``gemini_joiner/archive/`` (or legacy ``gemini_flash_system``)."""
    for family in ("gemini_joiner", "gemini_flash_system"):
        archive = _PROMPTS_ROOT / family / "archive"
        if archive.is_dir():
            return sorted(p.name for p in archive.glob("v*.md"))
    return []
