from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import import_module
from pathlib import Path

from pipeline.input.image_validation import (
    ImageValidationError,
    MismatchAbortError,
    MismatchPolicy,
)
from pipeline.input.completeness_gate import (
    CompletenessPolicy,
    InputCompletenessAbortError,
    InputCompletenessPause,
    INPUT_GAPS_EXIT_CODE,
)
from pipeline.input.ingest import run_ingest_pipeline
from pipeline.input.resume_input import continue_after_input_gaps, input_root_from_manifest
from pipeline.input.research_continue import ResearchContinuation

_builtin_input = import_module("builtins").input

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_env() -> None:
    from dotenv import load_dotenv

    from backend.runs.provider_log import normalize_provider_env

    load_dotenv(_REPO_ROOT / ".env")
    normalize_provider_env()


def _print_provider_status() -> None:
    from backend.runs.provider_log import provider_status_lines

    for line in provider_status_lines():
        print(line, flush=True)


def _stdin_is_interactive() -> bool:
    """True only for direct CLI use with a real terminal (not API subprocess)."""
    if os.environ.get("AUTOPAPER_NON_INTERACTIVE"):
        return False
    return sys.stdin.isatty()


def _run_editor(
    run_path: Path,
    ieee_format: str,
    *,
    verbose_log: bool = True,
    resume: bool = False,
) -> None:
    """Run the editor pipeline on a completed execution directory."""
    from pipeline.editor.pipeline import run_editor_pipeline
    from pipeline.editor.schemas import IeeeFormat

    fmt: IeeeFormat = "conference" if ieee_format == "conference" else "journal"
    if not verbose_log:
        print(f"\nEditor pipeline starting (format: {fmt}) …")
    if resume:
        print(f"Editor resume: reusing artifacts in {run_path}", flush=True)
    result = run_editor_pipeline(
        run_path, ieee_format=fmt, verbose_log=verbose_log, resume=resume
    )

    ok_sections = len(result.successful_sections)
    total_sections = len(result.sections)
    ok_figures = len(result.successful_figures)
    total_figures = len(result.figures)

    pass_count = sum(1 for v in result.validation if v.verdict == "pass")
    warn_count = sum(1 for v in result.validation if v.verdict == "warn")
    fail_count = sum(1 for v in result.validation if v.verdict == "fail")

    print(f"  Sections : {ok_sections}/{total_sections} OK")
    print(f"  Figures  : {ok_figures}/{total_figures} OK")
    print(f"  Validation: {pass_count} pass / {warn_count} warn / {fail_count} fail")
    if result.manuscript_tex:
        ms_dir = run_path / "13_ieee_manuscript"
        print(f"  Manuscript: {ms_dir / 'main.tex'}")
    if result.pdf_path:
        print(f"  PDF       : {result.pdf_path}")
    if result.errors:
        print("  Editor errors:", file=sys.stderr)
        for err in result.errors:
            print(f"    - {err}", file=sys.stderr)


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
            "See pipeline/input/README.md"
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
    parser.add_argument(
        "--ieee-edit",
        action="store_true",
        help=(
            "After research completes, run the editor pipeline to produce an IEEE manuscript "
            "(09_editor_plan.json → 13_ieee_manuscript/main.tex)."
        ),
    )
    parser.add_argument(
        "--ieee-format",
        choices=["journal", "conference"],
        default="journal",
        help="IEEE document class to use (default: journal).",
    )
    parser.add_argument(
        "--log-editor",
        action="store_true",
        help="Print live step-by-step editor pipeline log to stderr (always written to editor_run.log).",
    )
    parser.add_argument(
        "--execution-dir",
        default=None,
        metavar="PATH",
        help="Existing output/execution_NNN directory (required with --editor-only).",
    )
    parser.add_argument(
        "--editor-only",
        action="store_true",
        help="Run only the editor on --execution-dir (skip ingest and research).",
    )
    parser.add_argument(
        "--editor-resume",
        action="store_true",
        help="With --editor-only: reuse 09_editor_plan.json and 10_sections/; continue figures onward.",
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
    gaps = parser.add_mutually_exclusive_group()
    gaps.add_argument(
        "--force-continue-on-input-gaps",
        action="store_true",
        help="Proceed when input is incomplete without prompting (not recommended).",
    )
    gaps.add_argument(
        "--strict-input-gaps",
        action="store_true",
        help="Stop when required input data is missing (no prompt).",
    )
    parser.add_argument(
        "--continue-after-gaps",
        action="store_true",
        help=(
            "Resume from an existing execution dir after user supplements "
            "(requires --execution-dir and --input)."
        ),
    )
    parser.add_argument(
        "--supplement-json",
        default=None,
        metavar="PATH",
        help="JSON file with { \"answers\": { \"gap_id\": \"text\" } } for --continue-after-gaps.",
    )
    args = parser.parse_args(argv)

    _load_env()
    if (
        not args.editor_only
        and not args.continue_after_gaps
        and not os.environ.get("AUTOPAPER_QUIET_STARTUP")
    ):
        _print_provider_status()

    if args.continue_after_gaps:
        if not args.execution_dir or not args.input:
            print(
                "--continue-after-gaps requires both --execution-dir and --input.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        run_path = Path(args.execution_dir).expanduser().resolve()
        root = Path(args.input).expanduser().resolve()
        supplement_answers: dict[str, str] | None = None
        if args.supplement_json:
            raw = json.loads(Path(args.supplement_json).read_text(encoding="utf-8"))
            if isinstance(raw.get("answers"), dict):
                supplement_answers = {str(k): str(v) for k, v in raw["answers"].items()}
            elif isinstance(raw, dict):
                supplement_answers = {str(k): str(v) for k, v in raw.items()}
        if args.no_research:
            research_mode = ResearchContinuation.OFF
        elif args.full_research:
            research_mode = ResearchContinuation.FULL
        else:
            research_mode = ResearchContinuation.PLAN
        if args.strict_input_gaps:
            gap_policy = CompletenessPolicy.STRICT
        elif args.force_continue_on_input_gaps:
            gap_policy = CompletenessPolicy.CONTINUE
        else:
            gap_policy = CompletenessPolicy.AUTO
        try:
            continue_after_input_gaps(
                root,
                run_path,
                research=research_mode,
                supplement_answers=supplement_answers,
                completeness_policy=gap_policy,
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Run directory: {run_path.resolve()}")
        if args.ieee_edit:
            try:
                _run_editor(run_path, args.ieee_format, verbose_log=getattr(args, "log_editor", True))
            except Exception as exc:
                print(f"Editor pipeline failed: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
        return

    if args.editor_only:
        if not args.execution_dir:
            print("--execution-dir PATH is required with --editor-only.", file=sys.stderr)
            raise SystemExit(2)
        run_path = Path(args.execution_dir).expanduser().resolve()
        if not run_path.is_dir():
            print(f"Not a directory: {run_path}", file=sys.stderr)
            raise SystemExit(2)
        try:
            _run_editor(
                run_path,
                args.ieee_format,
                verbose_log=getattr(args, "log_editor", True),
                resume=args.editor_resume,
            )
        except Exception as exc:
            print(f"Editor pipeline failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return

    if getattr(args, "log_gemini", False):
        from backend.logging import enable_llm_trace

        enable_llm_trace()

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

    if args.strict_input_gaps:
        completeness_policy = CompletenessPolicy.STRICT
    elif args.force_continue_on_input_gaps:
        completeness_policy = CompletenessPolicy.CONTINUE
    else:
        completeness_policy = CompletenessPolicy.AUTO

    try:
        _, run_path = run_ingest_pipeline(
            root,
            output_root=out_arg,
            research=research_mode,
            mismatch_policy=mismatch_policy,
            completeness_policy=completeness_policy,
            stdin_is_tty=_stdin_is_interactive(),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except InputCompletenessPause as exc:
        print(str(exc), file=sys.stderr)
        print(f"Run directory: {exc.run_path.resolve()}")
        raise SystemExit(INPUT_GAPS_EXIT_CODE) from exc
    except (InputCompletenessAbortError, ImageValidationError, MismatchAbortError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except (RuntimeError, ImportError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Run directory: {run_path.resolve()}")

    if args.ieee_edit:
        try:
            _run_editor(run_path, args.ieee_format, verbose_log=getattr(args, "log_editor", True))
        except Exception as exc:
            print(f"Editor pipeline failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
