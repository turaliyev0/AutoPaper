from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

from paper_input.image_validation import (
    ImageValidationError,
    MismatchAbortError,
    MismatchPolicy,
)
from paper_input.ingest import run_ingest_pipeline
from paper_input.research_continue import ResearchContinuation

_builtin_input = import_module("builtins").input


def _resolve_root(args: argparse.Namespace) -> Path:
    if args.input:
        return Path(args.input).expanduser().resolve()
    if not sys.stdin.isatty():
        print("Pass --input FOLDER (no TTY).", file=sys.stderr)
        raise SystemExit(2)
    raw = _builtin_input("Input folder path: ").strip().strip('"').strip("'")
    if not raw:
        print("Empty path.", file=sys.stderr)
        raise SystemExit(2)
    return Path(raw).expanduser().resolve()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest paper folder → output/execution_NNN/ (steps 01–04), then by default "
            "research orchestrator plan (05). Requires GOOGLE_API_KEY and OPENAI_API_KEY for full research. "
            "Flow: src/autopaper/flow/paper_input/README.md"
        )
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Paper project folder. If omitted, prompts when TTY.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Folder that will contain execution_NNN/ (default: <repo>/output or AUTOPAPER_OUTPUT_DIR).",
    )
    research = parser.add_mutually_exclusive_group()
    research.add_argument(
        "--no-research",
        action="store_true",
        help="Stop after step 04 (no orchestrator).",
    )
    research.add_argument(
        "--full-research",
        action="store_true",
        help="After 04: orchestrator + all search agents + final report (05–07).",
    )
    parser.add_argument(
        "--log-gemini",
        action="store_true",
        help="Print Gemini API calls (and OpenAI orchestrator tools) to stderr.",
    )
    mismatch = parser.add_mutually_exclusive_group()
    mismatch.add_argument(
        "--force-continue-on-mismatch",
        action="store_true",
        help="Proceed after figure–text mismatch warnings without prompting.",
    )
    mismatch.add_argument(
        "--strict",
        action="store_true",
        help="Stop when joiner reports figure–text mismatches (no prompt).",
    )
    args = parser.parse_args(argv)

    if getattr(args, "log_gemini", False):
        import os

        os.environ["AUTOPAPER_LOG_TOOLS"] = "1"

    root = _resolve_root(args)
    out_arg = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    if args.no_research:
        research_mode = ResearchContinuation.OFF
    elif args.full_research:
        research_mode = ResearchContinuation.FULL
    else:
        research_mode = ResearchContinuation.PLAN

    if args.strict:
        mismatch_policy = MismatchPolicy.ABORT
    elif args.force_continue_on_mismatch:
        mismatch_policy = MismatchPolicy.CONTINUE
    else:
        mismatch_policy = MismatchPolicy.AUTO

    try:
        _, run_path = run_ingest_pipeline(
            root,
            output_root=out_arg,
            research=research_mode,
            mismatch_policy=mismatch_policy,
            stdin_is_tty=sys.stdin.isatty(),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except (ImageValidationError, MismatchAbortError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except (RuntimeError, ImportError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Run directory: {run_path.resolve()}")


if __name__ == "__main__":
    main()
