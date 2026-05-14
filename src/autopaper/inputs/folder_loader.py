from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autopaper.inputs.models import ResearchInput

TEXT_GLOB_ORDER = ("*.md", "*.txt", "*.rst")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff"}


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
        out.setdefault("text_files", []).append(
            {"file": fp.name, "content": fp.read_text(encoding="utf-8").strip()}
        )
    return out


def expected_subpaths() -> tuple[tuple[str, ...], ...]:
    return (
        ("description",),
        ("details",),
        ("images",),
        ("metadata",),
    )


def ensure_input_layout(root: Path) -> None:
    """Create the standard input subtree if any part is missing."""
    root.mkdir(parents=True, exist_ok=True)
    for parts in expected_subpaths():
        (root.joinpath(*parts)).mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class FolderLoadResult:
    root: Path
    description: str
    details: str
    images_manifest: str
    metadata: dict[str, Any] = field(default_factory=dict)
    title: str | None = None

    def to_research_input(self, default_details: str) -> ResearchInput:
        details = self.details.strip() or default_details
        tech_parts: list[str] = []
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
            description=self.description.strip() or "(no text files in description/)",
            details=details,
            technical_details=technical,
            extra_context=extra,
        )


def load_input_folder(root: Path) -> FolderLoadResult:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input folder does not exist or is not a directory: {root}")

    description = _read_text_files(root / "description", "description")
    details = _read_text_files(root / "details", "details")
    images = _list_images(root / "images", root)
    metadata = _load_metadata_dict(root / "metadata")

    title: str | None = None
    if isinstance(metadata.get("paper"), dict):
        t = metadata["paper"].get("title")
        if isinstance(t, str) and t.strip():
            title = t.strip()

    return FolderLoadResult(
        root=root,
        description=description,
        details=details,
        images_manifest=images,
        metadata=metadata,
        title=title,
    )
