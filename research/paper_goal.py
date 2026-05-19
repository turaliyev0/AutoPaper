"""Build research orchestrator input from ``04_final_standardized.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .manuscript_context import ManuscriptContext, manuscript_context_from_standardized


def load_final_standardized(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def final_standardized_to_research_goal(
    data: dict[str, Any],
    *,
    ctx: ManuscriptContext | None = None,
) -> str:
    """Turn Joiner output into a research goal for SearchOrchestrator."""
    summary = str(data.get("summary") or "").strip()
    if not summary:
        raise ValueError("04_final_standardized.json has no summary")

    if ctx is None:
        ctx = manuscript_context_from_standardized(data)

    lines = [
        "Use the following standardized paper project bundle as the research subject.",
        "Plan subtopics for literature and contextual research that strengthen, contextualize, and "
        "validate this work (methods, comparable studies, materials, and metrics).",
        "",
        "## Summary",
        summary,
    ]

    block = ctx.to_orchestrator_block()
    if block:
        lines.extend(["", "## Manuscript context (structured)", block])

    return "\n".join(lines).strip()


def goal_from_execution_dir(execution_dir: Path) -> str:
    final_path = execution_dir / "04_final_standardized.json"
    if not final_path.is_file():
        raise FileNotFoundError(f"Missing {final_path}")
    data = load_final_standardized(final_path)
    ctx = manuscript_context_from_standardized(data)
    return final_standardized_to_research_goal(data, ctx=ctx)
