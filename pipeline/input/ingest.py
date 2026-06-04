from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .image_validation import (
    MismatchPolicy,
    assert_images_usable,
    collect_mismatch_warnings,
    resolve_mismatch_continuation,
)
from .completeness_gate import (
    CompletenessPolicy,
    InputCompletenessAbortError,
    InputCompletenessPause,
    resolve_completeness_continuation,
)
from .completeness import analyze_completeness
from .supplement import (
    persist_supplement_answers,
    refresh_standardized_after_supplements,
    write_supplement_files,
)
from .finalize import finalize_without_images
from .layout import IMAGE_SUFFIXES, TEXT_GLOB_ORDER, ensure_input_layout
from .research_continue import ResearchContinuation, continue_research
from .run_workspace import (
    allocate_execution_directory,
    append_run_manifest_steps,
    resolve_pipeline_output_root,
    write_run_manifest,
)

# Step 01: disk ingest
RAW_BUNDLE_FILENAME = "01_raw_input_bundle.json"
# Step 1 — Text Parser Agent
CLEANED_TEXT_FILENAME = "02_cleaned_text.json"
# Step 2 — Vision Agent
CLEANED_IMAGES_FILENAME = "03_cleaned_images.json"
# Step 3 — Joiner Agent
FINAL_STANDARDIZED_FILENAME = "04_final_standardized.json"


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"<read error: {exc}>"


def _collect_texts_under(root: Path, *subdir_parts: str) -> list[dict[str, Any]]:
    base = root.joinpath(*subdir_parts)
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for pattern in TEXT_GLOB_ORDER:
        for fp in sorted(base.glob(pattern), key=lambda p: p.name.lower()):
            if fp.is_file():
                rel = fp.relative_to(root).as_posix()
                items.append({"relative_path": rel, "content": _read_text_file(fp)})
    return items


def _collect_metadata_json(root: Path) -> list[dict[str, Any]]:
    meta = root / "metadata"
    if not meta.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for fp in sorted(meta.glob("*.json"), key=lambda p: p.name.lower()):
        rel = fp.relative_to(root).as_posix()
        raw = _read_text_file(fp)
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            parsed = {"_parse_error": str(exc), "_raw_preview": raw[:2000]}
        out.append({"relative_path": rel, "parsed": parsed})
    return out


def _list_image_paths(root: Path) -> list[str]:
    img_dir = root / "images"
    if not img_dir.is_dir():
        return []
    paths: list[str] = []
    for p in sorted(img_dir.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
            paths.append(p.relative_to(root).as_posix())
    return paths


def load_raw_input_bundle(root: Path) -> dict[str, Any]:
    """Load text under description/ and details/, metadata JSON, and image paths (no bytes)."""
    root = root.expanduser().resolve()
    return {
        "input_root": root.as_posix(),
        "description_files": _collect_texts_under(root, "description"),
        "details_files": _collect_texts_under(root, "details"),
        "metadata_json_files": _collect_metadata_json(root),
        "image_paths": _list_image_paths(root),
    }


def run_ingest_pipeline(
    root: Path,
    *,
    output_root: Path | None = None,
    research: ResearchContinuation = ResearchContinuation.PLAN,
    mismatch_policy: MismatchPolicy = MismatchPolicy.AUTO,
    completeness_policy: CompletenessPolicy = CompletenessPolicy.AUTO,
    supplement_answers: dict[str, str] | None = None,
    stdin_is_tty: bool | None = None,
) -> tuple[dict[str, Any], Path]:
    """
    Pipeline under ``<output>/execution_NNN/`` (see ``pipeline/input/README.md``):

    - **00** ``00_run_manifest.json``
    - **01** ``01_raw_input_bundle.json`` (disk)
    - **02** ``02_cleaned_text.json`` — Text Parser Agent
    - **03** ``03_cleaned_images.json`` — Vision Agent
    - **04** ``04_final_standardized.json`` — Joiner Agent
    - **05+** (optional) research orchestrator plan and, if enabled, search + report

    ``research``: ``off`` | ``plan`` (default) | ``full``.

    After step 03, unreadable images raise :class:`~pipeline.input.image_validation.ImageValidationError`.
    After step 04, non-empty ``mismatch_flags`` follow ``mismatch_policy`` (prompt / abort / continue).
    After step 04, :func:`analyze_completeness` may prompt for missing data (``completeness_policy``)
    before research starts.

    Returns ``(bundle, run_path)``.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    ensure_input_layout(root)

    run_path = allocate_execution_directory(
        resolve_pipeline_output_root(override=output_root),
    )

    bundle = load_raw_input_bundle(root)

    (run_path / RAW_BUNDLE_FILENAME).write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_run_manifest(
        run_path,
        pipeline="input_ingest",
        input_root=root,
        extra={"steps": ["00_run_manifest.json", RAW_BUNDLE_FILENAME]},
    )

    from pipeline.input.agents.text_parser_agent import TextParserAgent
    from pipeline.input.agents.vision_agent import VisionAgent
    from pipeline.input.agents.joiner_agent import JoinerAgent

    print("[STEP] Parsing paper text and metadata", flush=True)
    cleaned_text = TextParserAgent(bundle).run()
    (run_path / CLEANED_TEXT_FILENAME).write_text(
        json.dumps(cleaned_text, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_run_manifest_steps(run_path, CLEANED_TEXT_FILENAME)

    n_images = len(bundle.get("image_paths", []))
    if n_images == 0:
        print("[STEP] No figures - skipping vision and joiner", flush=True)
        cleaned_images = {"images": []}
        (run_path / CLEANED_IMAGES_FILENAME).write_text(
            json.dumps(cleaned_images, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        append_run_manifest_steps(run_path, CLEANED_IMAGES_FILENAME)
        print("[STEP] Standardizing text-only manuscript", flush=True)
        final = finalize_without_images(cleaned_text)
    else:
        print(f"[STEP] Analyzing {n_images} figure(s) with vision AI", flush=True)
        cleaned_images = VisionAgent(bundle).run()
        (run_path / CLEANED_IMAGES_FILENAME).write_text(
            json.dumps(cleaned_images, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        append_run_manifest_steps(run_path, CLEANED_IMAGES_FILENAME)
        assert_images_usable(bundle, cleaned_images)
        print("[STEP] Joining text and image descriptions", flush=True)
        final = JoinerAgent().run(cleaned_text, cleaned_images)
    from pipeline.input.image_registry import apply_image_exclusions

    final = apply_image_exclusions(final)
    (run_path / FINAL_STANDARDIZED_FILENAME).write_text(
        json.dumps(final, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_run_manifest_steps(run_path, FINAL_STANDARDIZED_FILENAME)

    resolve_mismatch_continuation(
        collect_mismatch_warnings(final),
        policy=mismatch_policy,
        is_tty=stdin_is_tty,
    )

    report_before = analyze_completeness(final, bundle)
    gap_targets = {g.id: g.target_path for g in report_before.gaps}
    answers = resolve_completeness_continuation(
        final,
        bundle,
        input_root=root,
        run_path=run_path,
        policy=completeness_policy,
        is_tty=stdin_is_tty,
        prefilled_answers=supplement_answers,
    )
    if answers:
        print("[STEP] Applying user supplements to input", flush=True)
        write_supplement_files(root, answers, gap_targets=gap_targets)
        persist_supplement_answers(run_path, answers)
        final = refresh_standardized_after_supplements(root, run_path)
        report_after = analyze_completeness(final, bundle)
        if report_after.has_blocking_gaps and completeness_policy is CompletenessPolicy.STRICT:
            raise InputCompletenessAbortError(
                report_after,
                reason="Input still incomplete after supplements (--strict-input-gaps).",
            )

    continue_research(run_path, mode=research)

    return bundle, run_path
