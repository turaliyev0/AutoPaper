from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autopaper.inputs.folder_loader import IMAGE_SUFFIXES, TEXT_GLOB_ORDER


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
    """Load all input text files and asset paths from an input folder (no image bytes)."""
    root = root.expanduser().resolve()
    return {
        "input_root": root.as_posix(),
        "description_files": _collect_texts_under(root, "description"),
        "details_files": _collect_texts_under(root, "details"),
        "metadata_json_files": _collect_metadata_json(root),
        "image_paths": _list_image_paths(root),
    }


def truncate_bundle_for_llm(bundle: dict[str, Any], max_chars_per_file: int) -> dict[str, Any]:
    """Copy the bundle with long file bodies shortened for LLM context limits."""

    def trunc_text(s: str) -> tuple[str, bool]:
        if len(s) <= max_chars_per_file:
            return s, False
        return s[:max_chars_per_file] + "\n... [truncated for model context]", True

    out = json.loads(json.dumps(bundle))  # simple copy
    for key in ("description_files", "details_files"):
        for item in out.get(key, []):
            if isinstance(item, dict) and "content" in item:
                text, cut = trunc_text(str(item["content"]))
                item["content"] = text
                if cut:
                    item["content_was_truncated"] = True
    for item in out.get("metadata_json_files", []):
        if not isinstance(item, dict):
            continue
        raw_preview = json.dumps(item.get("parsed"), ensure_ascii=False)
        text, cut = trunc_text(raw_preview)
        item["parsed_json_preview"] = text
        item.pop("parsed", None)
        if cut:
            item["parsed_preview_was_truncated"] = True
    return out
