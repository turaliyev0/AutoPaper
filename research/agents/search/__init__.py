"""Parallel search agents (gemini_search + openai_search; claude/exa disabled)."""

from ...config import ACTIVE_SEARCH_AGENT_IDS
from .gemini_search import GeminiSearchAgent
from .openai_search import OpenAISearchAgent

SEARCH_AGENT_IDS = frozenset(
    {"gemini_search", "openai_search", "claude_search", "exa_search"},
)

__all__ = [
    "ACTIVE_SEARCH_AGENT_IDS",
    "GeminiSearchAgent",
    "OpenAISearchAgent",
    "SEARCH_AGENT_IDS",
]
