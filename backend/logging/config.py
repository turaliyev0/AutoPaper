"""Environment flags for verbose LLM / pipeline logging."""

from __future__ import annotations

import os

_TRACE_ENV = (
    "AUTOPAPER_LOG_TOOLS",
    "AUTOPAPER_GEMINI_LOG",
    "GEMINI_LOG_CALLS",
    "RESEARCH_LOG_TOOLS",
)


def llm_trace_enabled() -> bool:
    for name in _TRACE_ENV:
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def enable_llm_trace() -> None:
    os.environ["AUTOPAPER_LOG_TOOLS"] = "1"
