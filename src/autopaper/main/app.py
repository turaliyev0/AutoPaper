from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

from input.ingest import run_ingest_pipeline

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
            "Ensure paper input layout, allocate output/execution_NNN/, write bundle + manifest; "
            "run Gemini by default (use --no-ai to skip)."
        )
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Paper project folder. If omitted, prompts when TTY.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip Gemini; only write 01_raw_input_bundle.json (no 02_ai_extraction.json).",
    )
    args = parser.parse_args(argv)

    root = _resolve_root(args)

    try:
        _, run_path = run_ingest_pipeline(root, process_ai=not args.no_ai)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except (RuntimeError, ImportError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Run directory: {run_path.resolve()}")


if __name__ == "__main__":
    main()
