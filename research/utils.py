"""Shared utilities: JSON extraction, logging helpers."""

from __future__ import annotations

import json
import logging
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


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from LLM text (strict; no repair or retry)."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty LLM response; expected JSON object")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    return data


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
