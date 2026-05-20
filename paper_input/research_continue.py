"""Chain paper_input step 04 → research orchestrator (and optional full research)."""

from __future__ import annotations

import asyncio
import logging
import sys
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ResearchContinuation(str, Enum):
    OFF = "off"
    PLAN = "plan"
    FULL = "full"


async def continue_research_async(
    execution_dir: Path,
    *,
    mode: ResearchContinuation,
) -> None:
    if mode == ResearchContinuation.OFF:
        return

    from research.config import load_settings
    from research.paper_goal import goal_from_execution_dir
    from research.pipeline import ResearchPipeline, format_plan_summary

    goal = goal_from_execution_dir(execution_dir)
    plan_only = mode == ResearchContinuation.PLAN
    settings = load_settings()
    pipeline = ResearchPipeline(settings, plan_only=plan_only)
    result = await pipeline.run_in_execution_dir(execution_dir, goal)

    def _safe_print(text: str) -> None:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            ))

    _safe_print("")
    _safe_print("--- Research orchestrator plan ---")
    _safe_print(format_plan_summary(result.plan))
    print(f"\nPlan JSON: {execution_dir / '05_orchestrator_plan.json'}")
    if mode == ResearchContinuation.FULL:
        if result.bundle:
            ok = len(result.bundle.successful_results)
            total = len(result.bundle.results)
            print(f"Search tasks: {ok}/{total} succeeded")
        if result.validated:
            fails = sum(1 for v in result.validated.results if v.verdict == "fail")
            warns = sum(1 for v in result.validated.results if v.verdict == "warn")
            print(f"Validation: {len(result.validated.results)} tasks ({fails} fail, {warns} warn)")
        if result.report:
            print(f"Research index: {execution_dir / '08_research_index.md'}")
            print(f"Per-task files: {execution_dir / '06_research'}/")
    if result.errors:
        for err in result.errors:
            print(f"Warning: {err}", flush=True)


def continue_research(
    execution_dir: Path,
    *,
    mode: ResearchContinuation,
) -> bool:
    """Run research continuation. Returns True on success, False if skipped or failed."""
    try:
        asyncio.run(continue_research_async(execution_dir, mode=mode))
        return True
    except ValueError as exc:
        logger.warning("Research continuation skipped: %s", exc)
        print(f"Research step skipped: {exc}", flush=True)
        return False
    except Exception as exc:
        logger.exception("Research continuation failed")
        print(f"Research step failed (steps 01–04 are saved): {exc}", flush=True)
        return False
