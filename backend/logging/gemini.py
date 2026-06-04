"""Gemini request / response tracing to stderr."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from .config import llm_trace_enabled

logger = logging.getLogger("autopaper.logging.gemini")


def gemini_trace_enabled() -> bool:
    return llm_trace_enabled()


def _emit(block: str) -> None:
    for line in block.splitlines():
        print(f"[Gemini] {line}", file=sys.stderr, flush=True)
    logger.info("%s", block.replace("\n", " | "))


def _preview(text: str, limit: int = 240) -> str:
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    return one[: limit - 3] + "..."


def log_request(
    *,
    label: str,
    model: str,
    mode: str,
    tools: list[str] | None = None,
    user_preview: str = "",
) -> None:
    if not gemini_trace_enabled():
        return
    lines = [
        f"--- request [{label}] ---",
        f"model={model} mode={mode}",
    ]
    if tools:
        lines.append(f"tools={', '.join(tools)}")
    if user_preview:
        lines.append(f"input: {_preview(user_preview)}")
    _emit("\n".join(lines))


def _part_summary(part: Any) -> list[str]:
    out: list[str] = []
    text = getattr(part, "text", None)
    if text and str(text).strip():
        out.append(f"text: {_preview(str(text), 160)}")

    fc = getattr(part, "function_call", None)
    if fc is not None:
        name = getattr(fc, "name", None) or "?"
        args = getattr(fc, "args", None)
        try:
            args_str = json.dumps(dict(args) if args else {}, ensure_ascii=False)
        except (TypeError, ValueError):
            args_str = str(args)
        out.append(f"function_call: {name}({args_str})")

    fr = getattr(part, "function_response", None)
    if fr is not None:
        name = getattr(fr, "name", None) or "?"
        resp = getattr(fr, "response", None)
        try:
            resp_str = json.dumps(resp, ensure_ascii=False) if resp is not None else "{}"
        except (TypeError, ValueError):
            resp_str = str(resp)
        out.append(f"function_response: {name} -> {_preview(resp_str, 200)}")

    return out


def log_response(response: Any, *, label: str) -> None:
    if not gemini_trace_enabled():
        return
    lines = [f"--- response [{label}] ---"]
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        lines.append("(no candidates)")
        _emit("\n".join(lines))
        return

    cand = candidates[0]
    finish = getattr(cand, "finish_reason", None)
    if finish:
        lines.append(f"finish_reason={finish}")

    content = getattr(cand, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        text = getattr(response, "text", None) or ""
        if text:
            lines.append(f"text: {_preview(str(text), 300)}")
    else:
        for i, part in enumerate(parts):
            summaries = _part_summary(part)
            if summaries:
                lines.append(f"part[{i}]: " + " | ".join(summaries))
            else:
                lines.append(f"part[{i}]: (non-text part)")

    meta = getattr(cand, "grounding_metadata", None)
    if meta is not None:
        queries = getattr(meta, "web_search_queries", None) or []
        if queries:
            lines.append(f"grounding_queries={list(queries)[:5]}")
        chunks = getattr(meta, "grounding_chunks", None) or []
        if chunks:
            lines.append(f"grounding_chunks={len(chunks)}")

    _emit("\n".join(lines))
