"""Agent prompts: versioned assets under subfolders; use ``loader`` for runtime text."""

from .loader import (
    load_joiner_instruction,
    load_text_parser_instruction,
    load_vision_instruction,
    prompts_root,
)

__all__ = [
    "load_joiner_instruction",
    "load_text_parser_instruction",
    "load_vision_instruction",
    "prompts_root",
]
