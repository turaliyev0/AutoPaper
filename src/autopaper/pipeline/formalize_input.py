from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from autopaper.config import Settings
from autopaper.pipeline.consolidated_input import (
    build_consolidated_input,
    image_records_skipped,
)
from autopaper.pipeline.input_bundle import load_raw_input_bundle, truncate_bundle_for_llm
from autopaper.pipeline.openai_image_descriptions import describe_images_for_paths
from autopaper.pipeline.run_directory import allocate_run_directory, write_run_manifest
from autopaper.prompts.loader import build_input_formalization_run, load_image_description_prompts


def parse_model_json(text: str) -> dict[str, Any]:
    """Parse JSON from a future model reply (strips optional ```json fences)."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    return json.loads(s)


def write_model_response_placeholder(run_dir: Path) -> None:
    """Reserve step 04 until a text LLM is wired for formal JSON output."""
    body = {
        "status": "skipped",
        "reason": "No text model call in this build. Use 05_consolidated_input.json as the unified record.",
    }
    (run_dir / "04_model_response.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def _resolve_image_records(
    root: Path,
    raw: dict[str, Any],
    *,
    describe_images: bool,
    prompts_dir: Path | None,
    settings: Settings,
) -> list[dict[str, Any]]:
    paths = list(raw.get("image_paths") or [])
    if not describe_images:
        return image_records_skipped(root, paths, reason="describe_images_disabled")
    if not settings.openai_api_key:
        return image_records_skipped(root, paths, reason="no_openai_api_key")
    if not paths:
        return []
    sys_p, usr_p, _ = load_image_description_prompts(prompts_dir=prompts_dir)
    return await describe_images_for_paths(
        root, paths, settings=settings, system_prompt=sys_p, user_prompt=usr_p
    )


def run_input_formalization(
    root: Path,
    *,
    run_dir: Path | None = None,
    save_raw: bool = True,
    max_chars_per_file: int = 48_000,
    prompts_dir: Path | None = None,
    describe_images: bool = False,
) -> tuple[dict[str, Any], Path]:
    """
    Load input folder, write numbered artifacts under ``output/run_<folder_name>_<n>/``.

    Always writes ``05_consolidated_input.json`` merging raw bundle, truncation, prompt assembly,
    and per-image rows (vision descriptions when ``describe_images`` and OpenAI key are set).
    """
    root = root.expanduser().resolve()
    run_path = run_dir if run_dir is not None else allocate_run_directory(root)
    run_path.mkdir(parents=True, exist_ok=True)

    raw = load_raw_input_bundle(root)
    llm_bundle = truncate_bundle_for_llm(raw, max_chars_per_file)
    run_doc = build_input_formalization_run(llm_bundle, prompts_dir=prompts_dir)

    if save_raw:
        (run_path / "01_raw_input_bundle.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (run_path / "02_truncated_bundle_for_llm.json").write_text(
        json.dumps(llm_bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_path / "03_assembled_prompts.json").write_text(
        json.dumps(run_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_model_response_placeholder(run_path)

    settings = Settings()
    image_records = asyncio.run(
        _resolve_image_records(
            root,
            raw,
            describe_images=describe_images,
            prompts_dir=prompts_dir,
            settings=settings,
        )
    )
    consolidated = build_consolidated_input(
        raw_bundle=raw,
        truncated_bundle=llm_bundle,
        formalization_run=run_doc,
        image_records=image_records,
    )
    (run_path / "05_consolidated_input.json").write_text(
        json.dumps(consolidated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    steps = [
        "00_run_manifest.json",
        *(["01_raw_input_bundle.json"] if save_raw else []),
        "02_truncated_bundle_for_llm.json",
        "03_assembled_prompts.json",
        "04_model_response.json",
        "05_consolidated_input.json",
    ]
    write_run_manifest(
        run_path,
        pipeline="input_formalization",
        input_root=root,
        extra={
            "steps": steps,
            "describe_images": describe_images,
            "vision_model": settings.default_model_vision if describe_images else None,
        },
    )

    return run_doc, run_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create output/run_<input_folder_name>_<n>/ with numbered progress files; "
            "05_consolidated_input.json merges text ingest + prompts + per-image vision rows."
        )
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Input folder (description/, details/, images/, metadata/). Prompts if omitted and TTY.",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Use this directory instead of allocating a new output/run_<name>_<n>/.",
    )
    parser.add_argument(
        "--prompts-dir",
        default=None,
        help="Override prompts root (must contain manifest.json).",
    )
    parser.add_argument(
        "--describe-images",
        action="store_true",
        help="Call OpenAI vision (AUTOPAPER_OPENAI_API_KEY) for each image; descriptions go into 05 JSON.",
    )
    parser.add_argument(
        "--no-raw-bundle",
        action="store_true",
        help="Skip 01_raw_input_bundle.json (05 still contains full raw_input_bundle).",
    )
    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=48_000,
        help="Truncate each text file when building the truncated bundle.",
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

    explicit_run = Path(args.run_dir).expanduser().resolve() if args.run_dir else None

    pdir = Path(args.prompts_dir).expanduser().resolve() if args.prompts_dir else None

    _, run_path = run_input_formalization(
        root,
        run_dir=explicit_run,
        save_raw=not args.no_raw_bundle,
        max_chars_per_file=args.max_chars_per_file,
        prompts_dir=pdir,
        describe_images=args.describe_images,
    )
    print(f"Run directory: {run_path.resolve()}")


if __name__ == "__main__":
    main()
