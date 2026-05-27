"""Editor artifact layout inside output/execution_NNN/."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .schemas import EditorPlan, EditorRunResult, EditorValidationResult, FigureResult, SectionDraft

# Output file/dir names
EXEC_EDITOR_PLAN = "09_editor_plan.json"
EXEC_SECTIONS_DIR = "10_sections"
EXEC_FIGURES_DIR = "11_figures"
EXEC_EDITOR_VALIDATION_DIR = "12_editor_validation"
EXEC_MANUSCRIPT_DIR = "13_ieee_manuscript"
EXEC_EDITOR_INDEX_MD = "14_editor_index.md"

MANIFEST_FILENAME = "manifest.json"
MAIN_TEX_FILENAME = "main.tex"
REFERENCES_BIB_FILENAME = "references.bib"


def section_slug(section_id: str, heading: str) -> str:
    digest = hashlib.sha256(heading.encode()).hexdigest()[:6]
    safe = re.sub(r"[^\w]+", "_", heading.lower())[:30].strip("_")
    return f"{section_id}_{safe}_{digest}"


def load_editor_plan(run_dir: Path) -> EditorPlan | None:
    path = run_dir / EXEC_EDITOR_PLAN
    if not path.is_file():
        return None
    return EditorPlan.model_validate_json(path.read_text(encoding="utf-8"))


def load_section_drafts(run_dir: Path) -> list[SectionDraft]:
    sections_dir = run_dir / EXEC_SECTIONS_DIR
    manifest_path = sections_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    drafts: list[SectionDraft] = []
    for entry in manifest.get("sections", []):
        filename = entry.get("filename")
        if not filename:
            continue
        path = sections_dir / filename
        if path.is_file():
            drafts.append(SectionDraft.model_validate_json(path.read_text(encoding="utf-8")))
    return drafts


def figure_result_if_complete(figures_dir: Path, figure_id: str) -> FigureResult | None:
    """Return a success result when PNG already exists from a prior partial run."""
    png = figures_dir / f"{figure_id}.png"
    py = figures_dir / f"{figure_id}.py"
    if not png.is_file() or png.stat().st_size < 1024:
        return None
    return FigureResult(
        figure_id=figure_id,
        output_path=str(png.resolve()),
        code_path=str(py.resolve()) if py.is_file() else "",
        success=True,
        retries=0,
        validation_notes="Resumed from existing PNG on disk.",
    )


def write_editor_plan(run_dir: Path, plan: EditorPlan) -> Path:
    path = run_dir / EXEC_EDITOR_PLAN
    path.write_text(plan.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    return path


def write_sections(run_dir: Path, sections: list[SectionDraft]) -> Path:
    sections_dir = run_dir / EXEC_SECTIONS_DIR
    sections_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for idx, draft in enumerate(sections, start=1):
        slug = section_slug(draft.section_id, draft.heading)
        filename = f"{idx:02d}_{slug}.json"
        path = sections_dir / filename
        path.write_text(draft.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        manifest_entries.append({
            "index": idx,
            "slug": slug,
            "filename": filename,
            "section_id": draft.section_id,
            "heading": draft.heading,
            "success": draft.success,
            "word_count": draft.word_count,
        })

    manifest = {
        "sections_dir": EXEC_SECTIONS_DIR,
        "count": len(manifest_entries),
        "sections": manifest_entries,
    }
    (sections_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return sections_dir


def write_figures(run_dir: Path, figures: list[FigureResult]) -> Path:
    figures_dir = run_dir / EXEC_FIGURES_DIR
    figures_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for idx, fig in enumerate(figures, start=1):
        manifest_entries.append({
            "index": idx,
            "figure_id": fig.figure_id,
            "output_path": fig.output_path,
            "code_path": fig.code_path,
            "success": fig.success,
            "retries": fig.retries,
        })

    manifest = {
        "figures_dir": EXEC_FIGURES_DIR,
        "count": len(manifest_entries),
        "figures": manifest_entries,
    }
    (figures_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return figures_dir


def load_editor_validation(run_dir: Path) -> list[EditorValidationResult]:
    val_dir = run_dir / EXEC_EDITOR_VALIDATION_DIR
    manifest_path = val_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results: list[EditorValidationResult] = []
    for entry in manifest.get("sections", []):
        filename = entry.get("filename")
        if not filename:
            continue
        path = val_dir / filename
        if path.is_file():
            results.append(
                EditorValidationResult.model_validate_json(path.read_text(encoding="utf-8"))
            )
    return results


def append_editor_validation_result(
    run_dir: Path,
    result: EditorValidationResult,
) -> None:
    """Persist one section verdict immediately (survives partial runs / API reload)."""
    val_dir = run_dir / EXEC_EDITOR_VALIDATION_DIR
    val_dir.mkdir(parents=True, exist_ok=True)
    slug = section_slug(result.section_id, result.section_id)
    filename = f"{slug}.validation.json"
    (val_dir / filename).write_text(
        result.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    manifest_path = val_dir / MANIFEST_FILENAME
    manifest: dict[str, Any] = {"count": 0, "sections": []}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = [e for e in manifest.get("sections", []) if e.get("section_id") != result.section_id]
    entries.append({
        "slug": slug,
        "filename": filename,
        "section_id": result.section_id,
        "verdict": result.verdict,
        "score": result.score,
    })
    manifest["sections"] = entries
    manifest["count"] = len(entries)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def write_editor_validation(
    run_dir: Path,
    results: list[EditorValidationResult],
) -> Path:
    val_dir = run_dir / EXEC_EDITOR_VALIDATION_DIR
    val_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for result in results:
        slug = section_slug(result.section_id, result.section_id)
        filename = f"{slug}.validation.json"
        (val_dir / filename).write_text(
            result.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        manifest_entries.append({
            "slug": slug,
            "filename": filename,
            "section_id": result.section_id,
            "verdict": result.verdict,
            "score": result.score,
        })

    manifest = {"count": len(manifest_entries), "sections": manifest_entries}
    (val_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return val_dir


def write_manuscript(
    run_dir: Path,
    *,
    main_tex: str,
    references_bib: str = "",
) -> Path:
    ms_dir = run_dir / EXEC_MANUSCRIPT_DIR
    ms_dir.mkdir(parents=True, exist_ok=True)
    (ms_dir / MAIN_TEX_FILENAME).write_text(main_tex, encoding="utf-8")
    if references_bib:
        (ms_dir / REFERENCES_BIB_FILENAME).write_text(references_bib, encoding="utf-8")
    return ms_dir
