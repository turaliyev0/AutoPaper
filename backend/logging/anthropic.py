"""Anthropic request / response tracing to stderr."""

from __future__ import annotations

import logging
import sys

from .config import llm_trace_enabled

logger = logging.getLogger("autopaper.logging.anthropic")


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


def log_anthropic_request(
    *,
    label: str,
    model: str,
    mode: str,
    user_preview: str = "",
) -> None:
    lines = [f"--- request [{label}] ---", f"model={model} mode={mode}"]
    if user_preview:
        lines.append(f"input: {_preview(user_preview)}")
    emit("[Anthropic]", "\n".join(lines))


def log_anthropic_response(*, label: str, content: str) -> None:
    lines = [f"--- response [{label}] ---"]
    if content.strip():
        lines.append(f"text: {_preview(content, 400)}")
    else:
        lines.append("(empty content)")
    emit("[Anthropic]", "\n".join(lines))
