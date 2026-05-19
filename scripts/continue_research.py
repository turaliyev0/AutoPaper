#!/usr/bin/env python3
"""Continue research on an existing execution folder (steps 05-07)."""

from __future__ import annotations

import argparse
import asyncio
import os
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
        help="Print Gemini + OpenAI calls and orchestrator tool calls to stderr.",
    )
    parser.add_argument(
        "--force-replan",
        action="store_true",
        help="Re-run GPT-4o orchestrator even if 05_orchestrator_plan.json exists.",
    )
    args = parser.parse_args()

    if args.log_tools:
        os.environ["AUTOPAPER_LOG_TOOLS"] = "1"
    if args.force_replan:
        os.environ["RESEARCH_FORCE_REPLAN"] = "1"

    from paper_input.research_continue import ResearchContinuation, continue_research_async
    from research.paper_goal import goal_from_execution_dir

    mode = ResearchContinuation.PLAN if args.plan_only else ResearchContinuation.FULL
    execution_dir = args.execution_dir.expanduser().resolve()
    goal = goal_from_execution_dir(execution_dir)

    log_path = execution_dir / "research_trace.log"
    if args.log_tools:
        print(f"Logging enabled -> stderr and {log_path}", flush=True)

    class _Tee:
        def __init__(self, stream, file_path: Path) -> None:
            self._stream = stream
            self._file = file_path.open("w", encoding="utf-8")

        def write(self, data: str) -> int:
            self._stream.write(data)
            self._file.write(data)
            return len(data)

        def flush(self) -> None:
            self._stream.flush()
            self._file.flush()

    old_stderr = sys.stderr
    tee = None
    if args.log_tools:
        tee = _Tee(old_stderr, log_path)
        sys.stderr = tee  # type: ignore[assignment]

    try:
        print(
            f"Goal length: {len(goal)} chars from {execution_dir / '04_final_standardized.json'}",
            flush=True,
        )
        asyncio.run(continue_research_async(execution_dir, mode=mode))
    finally:
        if tee is not None:
            sys.stderr = old_stderr
            tee._file.close()
            print(f"Trace log saved: {log_path}", flush=True)


if __name__ == "__main__":
    main()
