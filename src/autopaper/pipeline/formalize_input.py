from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from autopaper.pipeline.input_bundle import load_raw_input_bundle, truncate_bundle_for_llm
from autopaper.prompts.loader import build_input_formalization_run

DEFAULT_RUN_FILENAME = "formalization_run.json"
DEFAULT_RAW_BUNDLE_FILENAME = "raw_input_bundle.json"


def parse_model_json(text: str) -> dict[str, Any]:
    """Parse JSON from a future model reply (strips optional ```json fences)."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    return json.loads(s)


def run_input_formalization(
    root: Path,
    *,
    out_json: Path | None = None,
    save_raw: bool = False,
    max_chars_per_file: int = 48_000,
    prompts_dir: Path | None = None,
) -> dict[str, Any]:
    """Load input folder, assemble versioned prompts + bundle; write formalization_run.json (no LLM)."""
    root = root.expanduser().resolve()
    raw = load_raw_input_bundle(root)
    llm_bundle = truncate_bundle_for_llm(raw, max_chars_per_file)
    run_doc = build_input_formalization_run(llm_bundle, prompts_dir=prompts_dir)

    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if save_raw:
        (out_dir / DEFAULT_RAW_BUNDLE_FILENAME).write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    out_path = out_json or (out_dir / DEFAULT_RUN_FILENAME)
    out_path.write_text(json.dumps(run_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_doc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Load input text into a bundle, assemble prompts from src/autopaper/prompts/ "
            "(manifest.json + one file per prompt version). Writes formalization_run.json; no model call."
        )
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Input folder (description/, details/, images/, metadata/). Prompts if omitted and TTY.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"Output JSON path (default: <input>/output/{DEFAULT_RUN_FILENAME})",
    )
    parser.add_argument(
        "--prompts-dir",
        default=None,
        help="Override prompts root (must contain manifest.json). For tests or forks.",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help=f"Also write <input>/output/{DEFAULT_RAW_BUNDLE_FILENAME} (full file contents).",
    )
    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=48_000,
        help="Truncate each text file when building the bundle embedded in the user message.",
    )
    args = parser.parse_args(argv)

    if args.input:
        root = Path(args.input).expanduser().resolve()
    else:
        if not sys.stdin.isatty():
            print("Pass --input FOLDER (no TTY).", file=sys.stderr)
            raise SystemExit(2)
        raw_in = input("Input folder path: ").strip().strip('"').strip("'")
        if not raw_in:
            print("Empty path.", file=sys.stderr)
            raise SystemExit(2)
        root = Path(raw_in).expanduser().resolve()

    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        raise SystemExit(2)

    out_path = Path(args.out).expanduser().resolve() if args.out else None
    pdir = Path(args.prompts_dir).expanduser().resolve() if args.prompts_dir else None

    run_input_formalization(
        root,
        out_json=out_path,
        save_raw=args.save_raw,
        max_chars_per_file=args.max_chars_per_file,
        prompts_dir=pdir,
    )
    dest = out_path or (root / "output" / DEFAULT_RUN_FILENAME)
    print(f"Wrote {dest.resolve()}")


if __name__ == "__main__":
    main()
