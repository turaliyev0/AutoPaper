from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from autopaper.config import Settings
from autopaper.generation.markdown import write_markdown
from autopaper.inputs import (
    ensure_input_layout,
    expected_subpaths,
    load_input_folder,
)
from autopaper.orchestration import Orchestrator
from autopaper.providers import GPTProvider

DEFAULT_INSTRUCTIONS = (
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
        help="Path to input folder (with notes/, prompts/, …). If omitted, you are prompted interactively.",
    )
    parser.add_argument(
        "--no-create-dirs",
        action="store_true",
        help="Do not create missing subfolders; exit if the layout is incomplete.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output markdown path (default: <input>/output/paper_draft.md)",
    )
    parser.add_argument(
        "--instructions-fallback",
        default=DEFAULT_INSTRUCTIONS,
        help="Used when prompts/ has no text files.",
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
    research = bundle.to_research_input(args.instructions_fallback)
    title = bundle.title or "Untitled Manuscript"
    out_path = Path(args.out) if args.out else (root / "output" / "paper_draft.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    settings = Settings()

    async def _run() -> None:
        gpt = GPTProvider(settings)
        try:
            orch = Orchestrator(
                research_llm=gpt,
                writing_llm=gpt,
                review_llm=gpt,
                title=title,
            )
            draft = await orch.run(research)
        finally:
            await gpt.aclose()
        write_markdown(draft, out_path)
        print(f"Wrote {out_path.resolve()}")

    asyncio.run(_run())


if __name__ == "__main__":
    main(sys.argv[1:])
