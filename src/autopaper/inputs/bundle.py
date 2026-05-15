from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autopaper.inputs.layout import IMAGE_SUFFIXES, TEXT_GLOB_ORDER


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
    """Load all text files under description/ and details/, metadata JSON, and image paths (no bytes)."""
    root = root.expanduser().resolve()
    return {
        "input_root": root.as_posix(),
        "description_files": _collect_texts_under(root, "description"),
        "details_files": _collect_texts_under(root, "details"),
        "metadata_json_files": _collect_metadata_json(root),
        "image_paths": _list_image_paths(root),
    }
