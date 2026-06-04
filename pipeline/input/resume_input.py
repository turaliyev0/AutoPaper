"""Resume pipeline after user supplements (post step 04, pre research)."""

from __future__ import annotations

import json
from pathlib import Path

from .completeness import analyze_completeness
from .completeness_gate import (
    CompletenessPolicy,
    InputCompletenessAbortError,
    load_gaps_file,
)
from .ingest import FINAL_STANDARDIZED_FILENAME, load_raw_input_bundle
from .research_continue import ResearchContinuation, continue_research
from .supplement import (
    persist_supplement_answers,
    refresh_standardized_after_supplements,
    write_supplement_files,
)


def continue_after_input_gaps(
    input_root: Path,
    execution_dir: Path,
    *,
    research: ResearchContinuation,
    supplement_answers: dict[str, str] | None = None,
    completeness_policy: CompletenessPolicy = CompletenessPolicy.AUTO,
) -> Path:
    """
    Apply optional supplements, refresh 04, then run research (and return execution dir).

    Used by CLI ``--continue-after-gaps`` and API supplement handler.
    """
    input_root = input_root.expanduser().resolve()
    execution_dir = execution_dir.expanduser().resolve()
    if not execution_dir.is_dir():
        raise FileNotFoundError(f"Not a directory: {execution_dir}")

    final_path = execution_dir / FINAL_STANDARDIZED_FILENAME
    if not final_path.is_file():
        raise FileNotFoundError(f"Missing {FINAL_STANDARDIZED_FILENAME} in {execution_dir}")

    bundle = load_raw_input_bundle(input_root)
    gaps_report = load_gaps_file(execution_dir)
    if gaps_report is None:
        final = json.loads(final_path.read_text(encoding="utf-8"))
        gaps_report = analyze_completeness(final, bundle)

    if supplement_answers:
        gap_targets = {g.id: g.target_path for g in gaps_report.gaps}
        write_supplement_files(input_root, supplement_answers, gap_targets=gap_targets)
        persist_supplement_answers(execution_dir, supplement_answers)
        refresh_standardized_after_supplements(input_root, execution_dir)
        bundle = load_raw_input_bundle(input_root)
        final = json.loads((execution_dir / FINAL_STANDARDIZED_FILENAME).read_text(encoding="utf-8"))
        report_after = analyze_completeness(final, bundle)
        if report_after.has_blocking_gaps and completeness_policy is CompletenessPolicy.STRICT:
            raise InputCompletenessAbortError(
                report_after,
                reason="Input still incomplete after supplements.",
            )

    continue_research(execution_dir, mode=research)
    return execution_dir


def input_root_from_manifest(execution_dir: Path) -> Path | None:
    manifest = execution_dir / "00_run_manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        raw = str(data.get("input_root") or "").strip()
        if raw:
            p = Path(raw)
            if p.is_dir():
                return p
    except (json.JSONDecodeError, OSError):
        pass
    return None
