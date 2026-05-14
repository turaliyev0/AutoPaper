from __future__ import annotations

from pathlib import Path
from typing import Any

from autopaper.pipeline.run_directory import utc_now_iso


def image_records_skipped(
    root: Path, relative_paths: list[str], *, reason: str | None = None
) -> list[dict[str, Any]]:
    """Placeholder rows when vision is off or unavailable."""
    root = root.resolve()
    return [
        {
            "relative_path": p,
            "absolute_path": str((root / p).resolve()),
            "vision_status": "skipped",
            "vision_error": reason,
            "vision_model": None,
            "ai_description": None,
        }
        for p in relative_paths
    ]


def build_consolidated_input(
    *,
    raw_bundle: dict[str, Any],
    truncated_bundle: dict[str, Any],
    formalization_run: dict[str, Any],
    image_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Single JSON document tying together raw ingest, truncated bundle, prompt assembly,
    and per-image vision results (descriptions or errors).
    """
    return {
        "schema_version": 1,
        "role": "unified_input_record",
        "generated_at_utc": utc_now_iso(),
        "input_root": raw_bundle.get("input_root"),
        "raw_input_bundle": raw_bundle,
        "truncated_bundle_for_llm": truncated_bundle,
        "input_formalization": formalization_run,
        "images": image_records,
    }
