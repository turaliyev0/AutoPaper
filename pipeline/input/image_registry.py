"""Derive usable vs excluded images from joiner output (mismatch, duplicates)."""

from __future__ import annotations

from typing import Any

# Mismatch severities that mean the image must not be reused downstream.
_EXCLUDE_MISMATCH_SEVERITIES = frozenset({"likely_mismatch"})


def excluded_image_paths(data: dict[str, Any]) -> frozenset[str]:
    """
    Paths (e.g. ``images/foo.png``) that must not appear in figures, reuse_path, or
    ``Images available`` lists for orchestrator / editor / research indexing.
    """
    paths: set[str] = set()

    for entry in data.get("excluded_images") or []:
        if not isinstance(entry, dict):
            continue
        p = entry.get("path") or entry.get("image_path") or ""
        if isinstance(p, str) and p.strip():
            paths.add(p.strip())

    for raw in data.get("mismatch_flags") or []:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "").strip().lower()
        if severity not in _EXCLUDE_MISMATCH_SEVERITIES:
            continue
        p = raw.get("image_path")
        if isinstance(p, str) and p.strip():
            paths.add(p.strip())

    for dup in data.get("duplicate_images") or []:
        if not isinstance(dup, dict):
            continue
        p = dup.get("duplicate")
        if isinstance(p, str) and p.strip():
            paths.add(p.strip())

    return frozenset(paths)


def apply_image_exclusions(data: dict[str, Any]) -> dict[str, Any]:
    """
    Enrich standardized JSON with ``excluded_images`` and per-image ``excluded`` flags.

    Safe to call multiple times (recomputes from mismatch/duplicate rules).
    """
    excluded_list: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in data.get("mismatch_flags") or []:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "").strip().lower()
        if severity not in _EXCLUDE_MISMATCH_SEVERITIES:
            continue
        p = str(raw.get("image_path") or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        excluded_list.append({
            "path": p,
            "reason": "likely_mismatch",
            "issue": str(raw.get("issue") or "").strip(),
        })

    for dup in data.get("duplicate_images") or []:
        if not isinstance(dup, dict):
            continue
        p = str(dup.get("duplicate") or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        excluded_list.append({
            "path": p,
            "reason": "duplicate",
            "issue": f"Duplicate of {dup.get('original', '')}".strip(),
        })

    data["excluded_images"] = excluded_list
    paths = excluded_image_paths(data)

    for img in data.get("images") or []:
        if not isinstance(img, dict):
            continue
        rel = str(img.get("relative_path") or "").strip()
        if rel in paths:
            img["excluded"] = True
            for ex in excluded_list:
                if ex["path"] == rel:
                    img["exclusion_reason"] = ex["reason"]
                    break
        elif "excluded" in img:
            img.pop("excluded", None)
            img.pop("exclusion_reason", None)

    return data


def usable_images(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Images that are readable and not excluded."""
    blocked = excluded_image_paths(data)
    out: list[dict[str, Any]] = []
    for img in data.get("images") or []:
        if not isinstance(img, dict):
            continue
        rel = str(img.get("relative_path") or "").strip()
        if rel in blocked:
            continue
        if img.get("readable", True) is False:
            continue
        out.append(img)
    return out
