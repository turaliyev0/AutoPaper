"""Per-task research artifacts on disk (one JSON file per search subtask)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .schemas import GatheredResearchBundle, GatheredTaskResult, ValidatedResearchBundle

RESEARCH_DIR_NAME = "research"
VALIDATION_DIR_NAME = "validation"
MANIFEST_FILENAME = "manifest.json"

# Paper-input execution layout (beside step 04).
EXEC_RESEARCH_DIR = "06_research"
EXEC_GATHERED_AGGREGATE = "06_gathered_research.json"
EXEC_VALIDATION_DIR = "07_validation"
EXEC_INDEX_MD = "08_research_index.md"
EXEC_INDEX_META = "08_research_index.meta.json"

# Standalone ``output/research_runs/run_NNN/``.
RUN_RESEARCH_DIR = "02_research"
RUN_GATHERED_AGGREGATE = "02_gathered_research.json"
RUN_VALIDATION_DIR = "03_validation"
RUN_INDEX_MD = "04_research_index.md"
RUN_INDEX_META = "04_research_index.meta.json"


def task_artifact_slug(agent_id: str, index: int, task: str) -> str:
    """Stable filename stem: ``01_gemini_search_topic_digest``."""
    digest = hashlib.sha256(task.encode("utf-8")).hexdigest()[:6]
    safe = re.sub(r"[^\w]+", "_", task.lower())[:36].strip("_")
    prefix = f"{index:02d}_{agent_id}"
    if safe:
        return f"{prefix}_{safe}_{digest}"
    return f"{prefix}_{digest}"


def write_research_bundle(
    run_dir: Path,
    bundle: GatheredResearchBundle,
    *,
    research_dir_name: str,
    aggregate_filename: str,
) -> Path:
    """Write one JSON per task plus manifest and aggregate bundle."""
    research_dir = run_dir / research_dir_name
    research_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for idx, result in enumerate(bundle.results, start=1):
        slug = task_artifact_slug(result.agent_id, idx, result.task)
        filename = f"{slug}.json"
        path = research_dir / filename
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        manifest_entries.append(
            {
                "index": idx,
                "slug": slug,
                "filename": filename,
                "agent_id": result.agent_id,
                "task": result.task,
                "success": result.success,
            },
        )

    manifest = {
        "research_dir": research_dir_name,
        "task_count": len(manifest_entries),
        "tasks": manifest_entries,
    }
    (research_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    aggregate_path = run_dir / aggregate_filename
    aggregate_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    return research_dir


def load_research_manifest(research_dir: Path) -> dict[str, Any]:
    path = research_dir / MANIFEST_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Missing research manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_task_result(research_dir: Path, filename: str) -> GatheredTaskResult:
    path = research_dir / filename
    return GatheredTaskResult.model_validate_json(path.read_text(encoding="utf-8"))


def write_validation_bundle(
    run_dir: Path,
    validated: ValidatedResearchBundle,
    *,
    validation_dir_name: str,
) -> Path:
    validation_dir = run_dir / validation_dir_name
    validation_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for entry in validated.results:
        filename = f"{entry.slug}.validation.json"
        path = validation_dir / filename
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        manifest_entries.append(
            {
                "slug": entry.slug,
                "filename": filename,
                "research_file": entry.research_filename,
                "agent_id": entry.agent_id,
                "verdict": entry.verdict,
            },
        )

    manifest = {
        "validation_dir": validation_dir_name,
        "task_count": len(manifest_entries),
        "tasks": manifest_entries,
    }
    (validation_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return validation_dir


def layout_for_run_dir(run_dir: Path) -> tuple[str, str, str, str]:
    """Return (research_dir, aggregate_file, validation_dir, index_md) names for this run root."""
    if (run_dir / EXEC_RESEARCH_DIR).is_dir() or (run_dir / "05_orchestrator_plan.json").is_file():
        return (
            EXEC_RESEARCH_DIR,
            EXEC_GATHERED_AGGREGATE,
            EXEC_VALIDATION_DIR,
            EXEC_INDEX_MD,
        )
    return (
        RUN_RESEARCH_DIR,
        RUN_GATHERED_AGGREGATE,
        RUN_VALIDATION_DIR,
        RUN_INDEX_MD,
    )
