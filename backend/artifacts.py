"""Safe read access to files under an execution directory."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

# Max artifact download / JSON load (10 MiB)
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024

# Well-known paths the UI may request (also allows any file under these prefixes)
ALLOWED_EXACT = frozenset({
    "04_final_standardized.json",
    "09_editor_plan.json",
    "08_research_index.md",
    "08_research_index.meta.json",
    "06_gathered_research.json",
    "05_orchestrator_plan.json",
    "editor_run.log",
    "00_run_manifest.json",
    "13_ieee_manuscript/main.tex",
    "13_ieee_manuscript/references.bib",
    "13_ieee_manuscript/main.pdf",
})

ALLOWED_PREFIXES = (
    "06_research/",
    "07_validation/",
    "10_sections/",
    "11_figures/",
    "12_editor_validation/",
    "13_ieee_manuscript/",
)


def _execution_root(execution_dir: str) -> Path:
    if not execution_dir:
        raise HTTPException(404, "Execution directory not set for this run")
    root = Path(execution_dir).resolve()
    if not root.is_dir():
        raise HTTPException(404, "Execution directory not found")
    return root


def normalize_relative_path(relative: str) -> str:
    rel = relative.replace("\\", "/").strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise HTTPException(400, "Invalid artifact path")
    return rel


def is_allowed_artifact(relative: str) -> bool:
    if relative in ALLOWED_EXACT:
        return True
    return any(relative.startswith(p) for p in ALLOWED_PREFIXES)


def resolve_artifact_file(execution_dir: str, relative: str) -> Path:
    rel = normalize_relative_path(relative)
    if not is_allowed_artifact(rel):
        raise HTTPException(403, f"Artifact path not allowed: {rel}")
    root = _execution_root(execution_dir)
    full = (root / rel).resolve()
    if not str(full).startswith(str(root)):
        raise HTTPException(403, "Path escapes execution directory")
    if not full.is_file():
        raise HTTPException(404, f"Artifact not found: {rel}")
    if full.stat().st_size > MAX_ARTIFACT_BYTES:
        raise HTTPException(413, "Artifact too large to return inline")
    return full


def list_artifacts(execution_dir: str) -> list[dict[str, str | int]]:
    root = _execution_root(execution_dir)
    out: list[dict[str, str | int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not is_allowed_artifact(rel):
            continue
        out.append({
            "path": rel,
            "size_bytes": path.stat().st_size,
        })
    return out


def read_artifact_json(execution_dir: str, relative: str) -> dict:
    full = resolve_artifact_file(execution_dir, relative)
    return json.loads(full.read_text(encoding="utf-8"))
