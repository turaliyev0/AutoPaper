"""Tests for paper_input.image_registry."""

from __future__ import annotations

from paper_input.image_registry import (
    apply_image_exclusions,
    excluded_image_paths,
    usable_images,
)


def test_likely_mismatch_excluded() -> None:
    data = {
        "images": [
            {"relative_path": "images/a.png", "readable": True},
            {"relative_path": "images/b.png", "readable": True},
        ],
        "mismatch_flags": [
            {
                "image_path": "images/b.png",
                "severity": "likely_mismatch",
                "issue": "Wrong comparison.",
            },
        ],
    }
    enriched = apply_image_exclusions(data)
    assert "images/b.png" in excluded_image_paths(enriched)
    assert len(usable_images(enriched)) == 1
    assert usable_images(enriched)[0]["relative_path"] == "images/a.png"
    assert enriched["images"][1].get("excluded") is True


def test_duplicate_secondary_excluded() -> None:
    data = {
        "images": [
            {"relative_path": "images/orig.png"},
            {"relative_path": "images/dup.png"},
        ],
        "duplicate_images": [{"original": "images/orig.png", "duplicate": "images/dup.png"}],
    }
    enriched = apply_image_exclusions(data)
    assert "images/dup.png" in excluded_image_paths(enriched)
    assert "images/orig.png" not in excluded_image_paths(enriched)
