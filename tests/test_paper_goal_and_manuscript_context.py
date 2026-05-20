"""research/paper_goal and manuscript_context (no API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.manuscript_context import (
    extract_experimental_design,
    manuscript_context_from_standardized,
)
from research.paper_goal import (
    final_standardized_to_research_goal,
    goal_from_execution_dir,
    load_final_standardized,
)


def _minimal_final(summary: str = "Study summary line.") -> dict:
    return {
        "summary": summary,
        "text_blocks": [],
        "metadata_notes": [],
        "images": [],
        "cross_references": [],
    }


def test_final_standardized_to_research_goal_contains_summary() -> None:
    data = _minimal_final("Chronic implants in rodents.")
    goal = final_standardized_to_research_goal(data)
    assert "Chronic implants" in goal
    assert "## Summary" in goal


def test_final_standardized_to_research_goal_requires_summary() -> None:
    with pytest.raises(ValueError, match="no summary"):
        final_standardized_to_research_goal({"summary": ""})


def test_manuscript_context_extracts_journal_and_mismatch() -> None:
    data = {
        "summary": "Rats n=12 hemispheric design comparing silicon left and polyimide right.",
        "metadata_notes": [
            {
                "relative_path": "metadata/paper_meta.json",
                "key_points": [
                    "target_journal: Nature Methods",
                    "authors_0_name: Doe",
                ],
            },
        ],
        "mismatch_flags": [
            {
                "image_path": "images/plot.png",
                "text_paths": ["description/x.md"],
                "issue": "Plot shows wrong comparison.",
                "severity": "likely_mismatch",
            },
        ],
        "text_blocks": [
            {
                "relative_path": "details/method_notes.txt",
                "technical_analysis": (
                    "CONTROL GROUP (Left Hemisphere): Silicon.\n"
                    "TEST GROUP (Right Hemisphere): Polyimide.\n"
                    "Channel Count: 32 channels per hemisphere.\n"
                ),
            },
        ],
    }
    ctx = manuscript_context_from_standardized(data)
    assert ctx.target_journal == "Nature Methods"
    assert len(ctx.mismatch_flags) == 1
    assert ctx.mismatch_flags[0].image_path == "images/plot.png"
    block = ctx.to_orchestrator_block()
    assert "hemispher" in block.lower() or "Polyimide" in block


def test_extract_experimental_design_from_details_block() -> None:
    data = {
        "summary": "Unrelated short summary without design keywords.",
        "text_blocks": [
            {
                "relative_path": "details/method_notes.txt",
                "technical_analysis": (
                    "IMPLANT CONFIGURATION (Hemispheric Control Design):\n"
                    "CONTROL GROUP (Left Hemisphere): Rigid Silicon.\n"
                    "Sprague-Dawley rats (n=12)\n"
                ),
            },
        ],
    }
    lines = extract_experimental_design(data)
    assert lines
    joined = " ".join(lines).lower()
    assert "hemispher" in joined or "silicon" in joined


def test_goal_from_execution_dir_reads_04(tmp_path: Path) -> None:
    data = _minimal_final("Loaded from disk fixture.")
    (tmp_path / "04_final_standardized.json").write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    goal = goal_from_execution_dir(tmp_path)
    assert "Loaded from disk fixture" in goal


def test_load_final_standardized_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "04_final_standardized.json"
    path.write_text('{"summary": "x", "extra": 1}', encoding="utf-8")
    loaded = load_final_standardized(path)
    assert loaded["summary"] == "x"
    assert loaded["extra"] == 1
