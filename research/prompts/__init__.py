"""Versioned research prompts — load via :mod:`research.prompts.loader`."""

from .loader import (
    load_gemini_search_instruction,
    load_openai_search_instruction,
    load_orchestrator_instruction,
    load_research_index_instruction,
    load_research_validator_instruction,
    prompts_root,
)

__all__ = [
    "load_gemini_search_instruction",
    "load_openai_search_instruction",
    "load_orchestrator_instruction",
    "load_research_index_instruction",
    "load_research_validator_instruction",
    "prompts_root",
]
