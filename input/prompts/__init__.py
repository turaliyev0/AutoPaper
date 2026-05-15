"""Agent prompts: versioned assets under subfolders; use ``loader`` for runtime text."""

from .loader import (
    list_gemini_flash_system_archive_versions,
    load_gemini_flash_system_instruction,
    load_gemini_image_description_instruction,
    prompts_root,
)

__all__ = [
    "list_gemini_flash_system_archive_versions",
    "load_gemini_flash_system_instruction",
    "load_gemini_image_description_instruction",
    "prompts_root",
]