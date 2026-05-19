"""Shared LLM call logging to stderr (Gemini + OpenAI)."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("autopaper.llm.trace")

_LOG_ENV = (
    "AUTOPAPER_LOG_TOOLS",
    "AUTOPAPER_GEMINI_LOG",
    "GEMINI_LOG_CALLS",
    "RESEARCH_LOG_TOOLS",
)


def llm_trace_enabled() -> bool:
    for name in _LOG_ENV:
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def _preview(text: str, limit: int = 280) -> str:
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    return one[: limit - 3] + "..."


def emit(prefix: str, block: str) -> None:
    if not llm_trace_enabled():
        return
    for line in block.splitlines():
        print(f"{prefix} {line}", file=sys.stderr, flush=True)
    logger.info("[%s] %s", prefix.strip("[]"), block.replace("\n", " | "))


def log_openai_request(
    *,
    label: str,
    model: str,
    mode: str,
    user_preview: str = "",
) -> None:
    lines = [f"--- request [{label}] ---", f"model={model} mode={mode}"]
    if user_preview:
        lines.append(f"input: {_preview(user_preview)}")
    emit("[OpenAI]", "\n".join(lines))


def log_openai_response(*, label: str, content: str) -> None:
    lines = [f"--- response [{label}] ---"]
    if content.strip():
        lines.append(f"text: {_preview(content, 400)}")
    else:
        lines.append("(empty content)")
    emit("[OpenAI]", "\n".join(lines))


def log_openai_tool_session_start(*, model: str, tool_names: list[str]) -> None:
    emit(
        "[OpenAI-tools]",
        f"--- orchestrator session ---\nmodel={model}\ntools={', '.join(tool_names)}",
    )


def log_openai_tool_turn(*, turn: int, tool_count: int) -> None:
    emit("[OpenAI-tools]", f"turn {turn}: model returned {tool_count} tool call(s)")


def log_openai_tool_call(name: str, raw_args: str, payload: dict[str, str]) -> None:
    emit("[OpenAI-tools]", f"call {name}({raw_args})")
    emit("[OpenAI-tools]", f"result {name} -> {payload}")


def log_openai_tool_done(*, turns: int, final_text: str = "") -> None:
    lines = [f"--- orchestrator done ({turns} turn(s)) ---"]
    if final_text.strip():
        lines.append(f"assistant: {_preview(final_text, 200)}")
    emit("[OpenAI-tools]", "\n".join(lines))
