from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from autopaper.generation.markdown import write_markdown
from autopaper.inputs import (
    ensure_input_layout,
    expected_subpaths,
    load_input_folder,
)
from autopaper.inputs.serialization import paper_draft_to_dict, research_input_to_dict
from autopaper.orchestration import Orchestrator
from autopaper.pipeline.run_directory import allocate_run_directory, write_run_manifest
from autopaper.providers import StubLLMProvider

DEFAULT_DETAILS_FALLBACK = (
    "Write an IEEE-style research draft using the materials in the input folder. "
    "Stay faithful to provided numbers and claims."
)


def _resolve_input_root(args: argparse.Namespace) -> Path:
    if args.input:
        return Path(args.input).expanduser().resolve()
    if not sys.stdin.isatty():
        print("No TTY for prompts: pass --input FOLDER", file=sys.stderr)
        raise SystemExit(2)
    raw = input("Input folder path: ").strip().strip('"').strip("'")
    if not raw:
        print("Empty path.", file=sys.stderr)
        raise SystemExit(2)
    return Path(raw).expanduser().resolve()


def _verify_layout(root: Path) -> None:
    missing: list[Path] = []
    for parts in expected_subpaths():
        p = root.joinpath(*parts)
        if not p.is_dir():
            missing.append(p)
    if missing:
        for p in missing:
            print(f"Missing directory: {p}", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Auto-Paper: load an input/ folder and generate a draft")
    parser.add_argument(
        "--input",
        default=None,
        help="Path to input folder (description/, details/, images/, metadata/). If omitted, you are prompted interactively.",
    )
    parser.add_argument(
        "--no-create-dirs",
        action="store_true",
        help="Do not create missing subfolders; exit if the layout is incomplete.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional extra path for the Markdown draft (always also written under the run folder).",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Optional run directory; default is a new output/run_<input_name>_<n>/ folder.",
    )
    parser.add_argument(
        "--details-fallback",
        default=DEFAULT_DETAILS_FALLBACK,
        help="Used when details/ has no text files.",
    )
    args = parser.parse_args(argv)

    root = _resolve_input_root(args)
    if args.no_create_dirs:
        if not root.is_dir():
            print(f"Input folder does not exist: {root}", file=sys.stderr)
            raise SystemExit(2)
        _verify_layout(root)
    else:
        ensure_input_layout(root)

    bundle = load_input_folder(root)
    research = bundle.to_research_input(args.details_fallback)
    title = bundle.title or "Untitled Manuscript"

    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else allocate_run_directory(root)
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "01_research_input.json").write_text(
        json.dumps(research_input_to_dict(research), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    async def _run() -> Path:
        llm = StubLLMProvider()
        try:
            orch = Orchestrator(
                research_llm=llm,
                writing_llm=llm,
                review_llm=llm,
                title=title,
            )
            draft = await orch.run(research)
        finally:
            await llm.aclose()

        md_path = run_dir / "02_paper_draft.md"
        write_markdown(draft, md_path)
        (run_dir / "03_paper_draft.json").write_text(
            json.dumps(paper_draft_to_dict(draft), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        extra_out = Path(args.out).expanduser().resolve() if args.out else None
        if extra_out is not None:
            extra_out.parent.mkdir(parents=True, exist_ok=True)
            write_markdown(draft, extra_out)

        steps = [
            "00_run_manifest.json",
            "01_research_input.json",
            "02_paper_draft.md",
            "03_paper_draft.json",
        ]
        if extra_out is not None:
            steps.append(f"copy:{extra_out.as_posix()}")
        write_run_manifest(
            run_dir,
            pipeline="paper_draft_stub",
            input_root=root,
            extra={"steps": steps, "title": title},
        )
        return md_path

    md_written = asyncio.run(_run())
    print(f"Run directory: {run_dir.resolve()}")
    print(f"Draft: {md_written.resolve()}")


if __name__ == "__main__":
    main(sys.argv[1:])
