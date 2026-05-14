from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autopaper.inputs.models import ResearchInput

TEXT_GLOB_ORDER = ("*.md", "*.txt", "*.rst")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff"}
MODEL_RESULT_SUFFIXES = {".md", ".txt", ".json"}
CSV_PREVIEW_ROWS = 40
MAX_JSON_CHARS = 120_000


def _iter_text_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    found: set[Path] = set()
    for pattern in TEXT_GLOB_ORDER:
        for p in sorted(directory.glob(pattern)):
            if p.is_file():
                found.add(p)
    return sorted(found, key=lambda x: x.name.lower())


def _read_text_files(directory: Path, label: str) -> str:
    parts: list[str] = []
    for fp in _iter_text_files(directory):
        try:
            body = fp.read_text(encoding="utf-8")
        except OSError:
            body = f"<unreadable: {fp.name}>"
        parts.append(f"### {label}: {fp.name}\n\n{body.strip()}\n")
    return "\n".join(parts).strip()


def _preview_csv(path: Path, max_rows: int) -> str:
    lines: list[str] = [f"File: {path.name}"]
    try:
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    lines.append(f"... ({max_rows}+ rows truncated)")
                    break
                lines.append(", ".join(cell[:500] for cell in row))
    except Exception as exc:  # noqa: BLE001 — surface any parse error as text
        lines.append(f"<csv read error: {exc}>")
    return "\n".join(lines)


def _load_csv_previews(datasets_csv: Path) -> str:
    if not datasets_csv.is_dir():
        return ""
    blocks: list[str] = []
    for csv_path in sorted(datasets_csv.glob("*.csv"), key=lambda p: p.name.lower()):
        blocks.append(_preview_csv(csv_path, CSV_PREVIEW_ROWS))
    return "\n\n".join(blocks).strip()


def _list_images(images_dir: Path, root: Path) -> str:
    if not images_dir.is_dir():
        return ""
    paths: list[str] = []
    for p in sorted(images_dir.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p
            paths.append(str(rel).replace("\\", "/"))
    if not paths:
        return ""
    return "Image paths (relative to input folder):\n" + "\n".join(f"- {x}" for x in paths)


def _read_model_results(model_results: Path) -> str:
    if not model_results.is_dir():
        return ""
    parts: list[str] = []
    files = [p for p in model_results.iterdir() if p.is_file() and p.suffix.lower() in MODEL_RESULT_SUFFIXES]
    for fp in sorted(files, key=lambda x: x.name.lower()):
        try:
            if fp.suffix.lower() == ".json":
                raw = fp.read_text(encoding="utf-8")
                if len(raw) > MAX_JSON_CHARS:
                    raw = raw[:MAX_JSON_CHARS] + "\n... (json truncated)"
                data = json.loads(raw)
                body = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                body = fp.read_text(encoding="utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            body = f"<read error: {exc}>"
        parts.append(f"### model_results: {fp.name}\n\n{body}\n")
    return "\n".join(parts).strip()


def _load_metadata_dict(metadata_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not metadata_dir.is_dir():
        return out
    for fp in sorted(metadata_dir.glob("*.json"), key=lambda x: x.name.lower()):
        try:
            out[fp.stem] = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            out[fp.stem] = {"_error": str(exc)}
    for fp in sorted(metadata_dir.glob("*.txt"), key=lambda x: x.name.lower()):
        out.setdefault("text_files", []).append({"file": fp.name, "content": fp.read_text(encoding="utf-8").strip()})
    return out


def expected_subpaths() -> tuple[tuple[str, ...], ...]:
    return (
        ("notes",),
        ("prompts",),
        ("datasets", "csv"),
        ("images",),
        ("model_results",),
        ("metadata",),
    )


def ensure_input_layout(root: Path) -> None:
    """Create the standard input/ subtree if any part is missing."""
    root.mkdir(parents=True, exist_ok=True)
    for parts in expected_subpaths():
        (root.joinpath(*parts)).mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class FolderLoadResult:
    root: Path
    notes: str
    prompts: str
    datasets_preview: str
    images_manifest: str
    model_results: str
    metadata: dict[str, Any] = field(default_factory=dict)
    title: str | None = None

    def to_research_input(self, default_instructions: str) -> ResearchInput:
        instructions = self.prompts.strip() or default_instructions
        tech_parts: list[str] = []
        if self.datasets_preview:
            tech_parts.append("## Dataset previews (CSV)\n\n" + self.datasets_preview)
        if self.images_manifest:
            tech_parts.append("## Figures\n\n" + self.images_manifest)
        if self.metadata:
            meta_blob = json.dumps(self.metadata, indent=2, ensure_ascii=False)
            if len(meta_blob) > 16_000:
                meta_blob = meta_blob[:16_000] + "\n... (metadata truncated)"
            tech_parts.append("## Loaded metadata (metadata/)\n\n" + meta_blob)
        technical = "\n\n".join(tech_parts).strip()
        extra: dict[str, Any] = {"input_root": str(self.root.resolve())}
        if self.metadata:
            extra["metadata"] = self.metadata
        return ResearchInput(
            notes=self.notes.strip() or "(no text files in notes/)",
            user_instructions=instructions,
            model_outputs=self.model_results.strip(),
            technical_details=technical,
            extra_context=extra,
        )


def load_input_folder(root: Path) -> FolderLoadResult:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input folder does not exist or is not a directory: {root}")

    notes = _read_text_files(root / "notes", "notes")
    prompts = _read_text_files(root / "prompts", "prompts")
    datasets = _load_csv_previews(root / "datasets" / "csv")
    images = _list_images(root / "images", root)
    model_results = _read_model_results(root / "model_results")
    metadata = _load_metadata_dict(root / "metadata")

    title: str | None = None
    if isinstance(metadata.get("paper"), dict):
        t = metadata["paper"].get("title")
        if isinstance(t, str) and t.strip():
            title = t.strip()

    return FolderLoadResult(
        root=root,
        notes=notes,
        prompts=prompts,
        datasets_preview=datasets,
        images_manifest=images,
        model_results=model_results,
        metadata=metadata,
        title=title,
    )
