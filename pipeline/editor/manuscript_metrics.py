"""Extract quantitative evidence and study parameters from step-04 manuscript JSON."""

from __future__ import annotations

import re
from typing import Any

_RESULTS_BLOCK = re.compile(r"results\s+summary", re.IGNORECASE)
_MEASURED_OUTCOME = re.compile(
    r"results\s+summary|"
    r"\d+(?:\.\d+)?\s*(?:×|x)\s*(?:increase|fold)|"
    r"\d+\s*kω|\d+\s*kohm|"
    r"→|->|"
    r"week\s*\d+\s*=\s*\d|"
    r"baseline\s+\d|"
    r"gfap\s+(?:flexible|rigid)\s+\d|"
    r"iba1\s+(?:flexible|rigid)\s+\d|"
    r"snr\s*\([^)]+\)\s*:\s*\d|"
    r"impedance.{0,30}\d{2,}\s*k",
    re.IGNORECASE,
)
_METHOD_ONLY_LINE = re.compile(
    r"threshold|significance threshold|sampling rate|band-pass|spike detection|"
    r"evaluation metrics|expected outcome|channel count|electrode spacing|"
    r"^\s*signal-to-noise ratio \(snr\)\s*$",
    re.IGNORECASE,
)
_DURATION_WEEKS = re.compile(
    r"(?:recording\s+)?duration\s*:\s*(\d+)\s*weeks?|"
    r"(\d+)\s*weeks?\s+chronic",
    re.IGNORECASE,
)
_METRIC_LINE = re.compile(
    r"impedance|snr|signal-to-noise|gfap|iba1|spike|neuron|khz|kω|kohm|"
    r"p\s*<|anova|n\s*=\s*\d|sample size|week\s*\d",
    re.IGNORECASE,
)


def _claim_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("claim") or item.get("text") or "").strip()
    return ""


def flatten_key_claims(data: dict[str, Any]) -> list[str]:
    """Top-level and per-block key_claims as plain strings (deduplicated)."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        text = _claim_text(raw)
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    for item in data.get("key_claims") or []:
        _add(item)
    for block in data.get("text_blocks") or []:
        if not isinstance(block, dict):
            continue
        for item in block.get("key_claims") or []:
            _add(item)
    return out


def _text_blob(data: dict[str, Any]) -> str:
    parts: list[str] = [str(data.get("summary") or "")]
    for block in data.get("text_blocks") or []:
        if isinstance(block, dict):
            parts.append(str(block.get("technical_analysis") or ""))
    return "\n".join(parts)


def has_measured_outcomes(manuscript_data: dict[str, Any]) -> bool:
    """True when step-04 includes reported outcome numbers (not only design specs)."""
    for block in manuscript_data.get("text_blocks") or []:
        if not isinstance(block, dict):
            continue
        path = str(block.get("relative_path") or "").lower()
        text = str(block.get("technical_analysis") or "")
        if _RESULTS_BLOCK.search(text):
            return True
        if "result" in path:
            for line in text.splitlines():
                line = line.strip()
                if line and _MEASURED_OUTCOME.search(line) and not _METHOD_ONLY_LINE.search(line):
                    return True
    blob = _text_blob(manuscript_data)
    for line in blob.splitlines():
        line = line.strip()
        if not line or _METHOD_ONLY_LINE.search(line):
            continue
        if _MEASURED_OUTCOME.search(line):
            return True
    return False


def quantitative_outcome_lines(manuscript_data: dict[str, Any]) -> list[str]:
    """
    Lines suitable for Abstract / Results / figure data_hints.

    Prefer explicit results-summary blocks; otherwise metric lines from all blocks.
    """
    lines: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        line = raw.strip().lstrip("-").strip()
        if not line or len(line) < 4:
            return
        if not _METRIC_LINE.search(line) and not _MEASURED_OUTCOME.search(line):
            return
        key = line.lower()
        if key in seen:
            return
        seen.add(key)
        lines.append(line[:240])

    for block in manuscript_data.get("text_blocks") or []:
        if not isinstance(block, dict):
            continue
        text = str(block.get("technical_analysis") or "")
        path = str(block.get("relative_path") or "").lower()
        in_results = "result" in path or _RESULTS_BLOCK.search(text)
        for line in text.splitlines():
            if _METHOD_ONLY_LINE.search(line):
                continue
            if in_results or (_MEASURED_OUTCOME.search(line)):
                _add(line)
            elif in_results and _METRIC_LINE.search(line):
                _add(line)

    if len(lines) < 3:
        for claim in flatten_key_claims(manuscript_data):
            _add(claim)

    return lines[:20]


def study_duration_weeks(manuscript_data: dict[str, Any]) -> int | None:
    """Chronic study length in weeks when stated in the manuscript (e.g. 12)."""
    blob = _text_blob(manuscript_data)
    best: int | None = None
    for m in _DURATION_WEEKS.finditer(blob):
        for g in m.groups():
            if g:
                n = int(g)
                if best is None or n > best:
                    best = n
    return best
