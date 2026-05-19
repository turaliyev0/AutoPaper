#!/usr/bin/env python3
"""Continue research on an existing execution folder (steps 05-07)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full research on execution_NNN/")
    parser.add_argument(
        "execution_dir",
        type=Path,
        help="Path to output/execution_NNN (must contain 04_final_standardized.json)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only re-run orchestrator (05), no search/report",
    )
    parser.add_argument(
        "--log-tools",
        action="store_true",
        help="Print Gemini calls and OpenAI orchestrator tool calls to stderr.",
    )
    args = parser.parse_args()

    if args.log_tools:
        import os

        os.environ["AUTOPAPER_LOG_TOOLS"] = "1"

    from paper_input.research_continue import ResearchContinuation, continue_research_async
    from research.paper_goal import goal_from_execution_dir

    mode = ResearchContinuation.PLAN if args.plan_only else ResearchContinuation.FULL
    execution_dir = args.execution_dir.expanduser().resolve()
    goal = goal_from_execution_dir(execution_dir)
    print(f"Goal length: {len(goal)} chars from {execution_dir / '04_final_standardized.json'}")
    asyncio.run(continue_research_async(execution_dir, mode=mode))


if __name__ == "__main__":
    main()
