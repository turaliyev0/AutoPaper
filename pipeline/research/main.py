"""CLI entry point for the Multi-Agent Research Pipeline."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import load_settings
from .pipeline import ResearchPipeline
from .research_storage import RUN_INDEX_MD
from .utils import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Multi-Agent Research Pipeline: GPT-4o orchestrator; "
            "parallel gemini_search + openai_search; Gemini validator; "
            "Gemini research index catalog."
        )
    )
    parser.add_argument(
        "goal",
        nargs="?",
        default=None,
        help="Research goal / topic (quoted string).",
    )
    parser.add_argument(
        "--goal-file",
        type=Path,
        default=None,
        help="Read research goal from a text/markdown file.",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help="Path to .env file (default: repo root .env).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override RESEARCH_OUTPUT_DIR for this run.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging.",
    )
    parser.add_argument(
        "--log-tools",
        action="store_true",
        help="Print Gemini calls and OpenAI orchestrator tool calls to stderr.",
    )
    return parser


def _resolve_goal(args: argparse.Namespace) -> str:
    if args.goal_file is not None:
        return args.goal_file.read_text(encoding="utf-8").strip()
    if args.goal:
        return args.goal.strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("Provide a research goal as an argument, --goal-file, or stdin.")


async def _async_main(args: argparse.Namespace) -> int:
    import os

    if args.log_tools:
        from backend.logging import enable_llm_trace

        enable_llm_trace()
    setup_logging()
    settings = load_settings(args.env)
    if args.output_dir is not None:
        settings = settings.model_copy(update={"research_output_dir": args.output_dir})

    goal = _resolve_goal(args)
    pipeline = ResearchPipeline(settings)
    result = await pipeline.run(goal)

    print(f"\nRun directory: {result.output_dir}")
    print(f"Topic: {result.plan.research_goal.main_topic}")
    if result.bundle:
        print(
            f"Search: {len(result.bundle.successful_results)}/{len(result.bundle.results)} tasks OK"
        )
    if result.validated:
        coverages = [v.coverage for v in result.validated.results]
        print(
            f"Validation: pass={coverages.count('pass')} "
            f"warn={coverages.count('warn')} fail={coverages.count('fail')} "
            f"(coverage sufficient={coverages.count('sufficient')})"
        )
    if result.report:
        print(f"Research index: {result.output_dir}/{RUN_INDEX_MD}")
    if result.errors:
        print("Warnings/errors:", file=sys.stderr)
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)
    raise SystemExit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
