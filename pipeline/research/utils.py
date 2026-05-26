"""Shared utilities: JSON extraction, logging helpers."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

def short_step_label(text: str, max_len: int = 100) -> str:
    """One-line label for progress logs (research task descriptions, etc.)."""
    one = " ".join(str(text).split())
    if len(one) <= max_len:
        return one
    return one[: max_len - 3] + "..."


JSON_ONLY_OUTPUT_RULE = (
    "The API is configured for JSON-only output. Reply with exactly one valid JSON object — "
    "no markdown fences, no prose, and no text before or after the object."
)


def _strip_markdown_fence(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_outer_json_object(text: str) -> str | None:
    """Return the first top-level `{...}` span using brace matching (string-aware)."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    quote = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _light_json_sanitize(text: str) -> str:
    """Fix common LLM JSON mistakes without a repair library."""
    s = text
    for src, dst in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
    ):
        s = s.replace(src, dst)
    s = re.sub(r",\s*}", "}", s)
    s = re.sub(r",\s*]", "]", s)
    return s


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from LLM text (strict json.loads; no json-repair library)."""
    stripped = _strip_markdown_fence(text)
    if not stripped:
        raise ValueError("Empty LLM response; expected JSON object")

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str | None) -> None:
        if not candidate:
            return
        c = candidate.strip()
        if c and c not in seen:
            seen.add(c)
            candidates.append(c)

    _add(stripped)
    outer = _extract_outer_json_object(stripped)
    _add(outer)
    if outer:
        _add(_light_json_sanitize(outer))
    _add(_light_json_sanitize(stripped))

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")
        return data

    detail = str(last_exc) if last_exc else "no parseable object"
    raise ValueError(f"LLM returned invalid JSON: {detail}") from last_exc


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
