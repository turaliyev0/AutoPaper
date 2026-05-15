from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autopaper.ingest import prepare_input_run


def _resolve_root(args: argparse.Namespace) -> Path:
    if args.input:
        return Path(args.input).expanduser().resolve()
    if not sys.stdin.isatty():
        print("Pass --input FOLDER (no TTY).", file=sys.stderr)
        raise SystemExit(2)
    raw = input("Input folder path: ").strip().strip('"').strip("'")
    if not raw:
        print("Empty path.", file=sys.stderr)
        raise SystemExit(2)
    return Path(raw).expanduser().resolve()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create output/run_<folder>_<n>/ and write 01_raw_input_bundle.json from description/, details/, images/, metadata/."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Input project folder. If omitted, prompts when TTY.",
    )
    parser.add_argument(
        "--no-create-dirs",
        action="store_true",
        help="Do not create missing layout; require description/, details/, images/, metadata/.",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Use this directory instead of allocating output/run_<name>_<n>/.",
    )
    args = parser.parse_args(argv)

    root = _resolve_root(args)
    explicit = Path(args.run_dir).expanduser().resolve() if args.run_dir else None

    try:
        _, run_path = prepare_input_run(
            root,
            run_dir=explicit,
            create_layout=not args.no_create_dirs,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Run directory: {run_path.resolve()}")


if __name__ == "__main__":
    main()
