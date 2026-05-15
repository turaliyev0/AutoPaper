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


def load_gemini_flash_system_instruction() -> str:
    """Return the active Gemini prompt for pipeline step 03 (render / restructure)."""
    return _load_family_prompt("gemini_flash_system")


def load_gemini_image_description_instruction() -> str:
    """Return the active Gemini prompt for pipeline step 02 (image descriptions)."""
    return _load_family_prompt("gemini_image_description")


def list_gemini_flash_system_archive_versions() -> list[str]:
    """Sorted archive filenames (e.g. ``v001.md``, ``v002.md``) under ``gemini_flash_system/archive/``."""
    archive = _PROMPTS_ROOT / "gemini_flash_system" / "archive"
    if not archive.is_dir():
        return []
    return sorted(p.name for p in archive.glob("v*.md"))
