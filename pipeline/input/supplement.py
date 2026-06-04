"""Apply user supplements to input folder and refresh step 04."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .finalize import finalize_without_images
from .run_workspace import append_run_manifest_steps

CLEANED_TEXT_FILENAME = "02_cleaned_text.json"
CLEANED_IMAGES_FILENAME = "03_cleaned_images.json"
FINAL_STANDARDIZED_FILENAME = "04_final_standardized.json"


def write_supplement_files(
    input_root: Path,
    answers: dict[str, str],
    *,
    gap_targets: dict[str, str],
) -> list[str]:
    """Write non-empty answers to target paths under input_root. Returns paths written."""
    written: list[str] = []
    input_root = input_root.expanduser().resolve()
    for gap_id, text in answers.items():
        text = str(text or "").strip()
        if not text:
            continue
        rel = gap_targets.get(gap_id)
        if not rel:
            continue
        dest = input_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file():
            existing = dest.read_text(encoding="utf-8").strip()
            combined = f"{existing}\n\n--- User supplement ---\n\n{text}" if existing else text
            dest.write_text(combined + "\n", encoding="utf-8")
        else:
            dest.write_text(text + "\n", encoding="utf-8")
        written.append(rel)
    return written


def refresh_standardized_after_supplements(
    input_root: Path,
    run_path: Path,
) -> dict[str, Any]:
    """
    Re-parse input and rebuild 02–04 after user supplements were added.

    Reuses vision output on disk when present (figures unchanged).
    """
    input_root = input_root.expanduser().resolve()
    run_path = run_path.expanduser().resolve()
    from .ingest import load_raw_input_bundle

    bundle = load_raw_input_bundle(input_root)

    from pipeline.input.agents.text_parser_agent import TextParserAgent
    from pipeline.input.agents.joiner_agent import JoinerAgent
    from pipeline.input.image_registry import apply_image_exclusions

    cleaned_text = TextParserAgent(bundle).run()
    (run_path / CLEANED_TEXT_FILENAME).write_text(
        json.dumps(cleaned_text, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_run_manifest_steps(run_path, CLEANED_TEXT_FILENAME)

    images_path = run_path / CLEANED_IMAGES_FILENAME
    n_images = len(bundle.get("image_paths") or [])
    if n_images == 0 or not images_path.is_file():
        final = finalize_without_images(cleaned_text)
    else:
        cleaned_images = json.loads(images_path.read_text(encoding="utf-8"))
        final = JoinerAgent().run(cleaned_text, cleaned_images)

    final = apply_image_exclusions(final)
    user_notes = run_path / "04_user_supplements.json"
    if user_notes.is_file():
        try:
            meta = json.loads(user_notes.read_text(encoding="utf-8"))
            final["user_supplements_applied"] = meta.get("answers_keys", [])
        except json.JSONDecodeError:
            pass

    (run_path / FINAL_STANDARDIZED_FILENAME).write_text(
        json.dumps(final, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_run_manifest_steps(run_path, FINAL_STANDARDIZED_FILENAME)
    return final


def persist_supplement_answers(run_path: Path, answers: dict[str, str]) -> None:
    path = run_path / "04_user_supplements.json"
    path.write_text(
        json.dumps(
            {
                "answers_keys": sorted(k for k, v in answers.items() if str(v).strip()),
                "answers": {k: v for k, v in answers.items() if str(v).strip()},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
