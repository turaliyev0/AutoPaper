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
            "Ingest paper folder → Output/execution_NNN/: raw bundle, Text Parser (02), "
            "Vision (03), Joiner (04). Requires GOOGLE_API_KEY or GEMINI_API_KEY."
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
        help="Folder that will contain execution_NNN/ (default: <repo>/Output or AUTOPAPER_OUTPUT_DIR).",
    )
    args = parser.parse_args(argv)

    root = _resolve_root(args)
    out_arg = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    try:
        _, run_path = run_ingest_pipeline(root, output_root=out_arg)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except (RuntimeError, ImportError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Run directory: {run_path.resolve()}")


if __name__ == "__main__":
    main()
