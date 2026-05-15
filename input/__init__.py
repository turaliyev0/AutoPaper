"""Paper input: layout, loading, run workspace, ingest, agents, prompts (all under this package)."""

from .ingest import (
    AI_EXTRACTION_FILENAME,
    CLEANED_IMAGES_FILENAME,
    CLEANED_TEXT_FILENAME,
    FINAL_STANDARDIZED_FILENAME,
    IMAGE_DESCRIPTIONS_FILENAME,
    RAW_BUNDLE_FILENAME,
    load_raw_input_bundle,
    run_ingest_pipeline,
)
from .layout import (
    ensure_input_layout,
    expected_subpaths,
    verify_input_layout,
)
from .run_workspace import (
    allocate_execution_directory,
    append_run_manifest_steps,
    resolve_pipeline_output_root,
    utc_now_iso,
    write_run_manifest,
)

__all__ = [
    "AI_EXTRACTION_FILENAME",
    "CLEANED_IMAGES_FILENAME",
    "CLEANED_TEXT_FILENAME",
    "FINAL_STANDARDIZED_FILENAME",
    "IMAGE_DESCRIPTIONS_FILENAME",
    "RAW_BUNDLE_FILENAME",
    "allocate_execution_directory",
    "append_run_manifest_steps",
    "ensure_input_layout",
    "expected_subpaths",
    "load_raw_input_bundle",
    "resolve_pipeline_output_root",
    "run_ingest_pipeline",
    "utc_now_iso",
    "verify_input_layout",
    "write_run_manifest",
]
