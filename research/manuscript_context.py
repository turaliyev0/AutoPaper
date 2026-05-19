"""Structured manuscript context for research steps (from ``04_final_standardized.json``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MismatchFlag(BaseModel):
    image_path: str = ""
    text_paths: list[str] = Field(default_factory=list)
    issue: str = ""
    severity: str = ""


class ManuscriptContext(BaseModel):
    """Passed to orchestrator search agents and synthesizer (research pipeline only)."""

    summary: str = ""
    target_journal: str = ""
    mismatch_flags: list[MismatchFlag] = Field(default_factory=list)
    metadata_key_points: list[str] = Field(default_factory=list)

    def to_orchestrator_block(self) -> str:
        lines: list[str] = []
        if self.target_journal:
            lines.append(f"Target journal: {self.target_journal}")
        if self.mismatch_flags:
            lines.append("Priority figure–text issues (must appear in required_outputs and openai_search):")
            for flag in self.mismatch_flags:
                lines.append(f"  - [{flag.severity or 'note'}] {flag.image_path}: {flag.issue}")
        if self.metadata_key_points:
            lines.append("Metadata highlights:")
            for point in self.metadata_key_points[:12]:
                lines.append(f"  - {point}")
        return "\n".join(lines)

    def to_search_dict(self) -> dict[str, Any]:
        return {
            "manuscript_summary_excerpt": self.summary[:2500] if self.summary else "",
            "target_journal": self.target_journal,
            "mismatch_flags": [f.model_dump() for f in self.mismatch_flags],
        }


def manuscript_context_from_standardized(data: dict[str, Any]) -> ManuscriptContext:
    flags: list[MismatchFlag] = []
    for raw in data.get("mismatch_flags") or []:
        if isinstance(raw, dict):
            flags.append(
                MismatchFlag(
                    image_path=str(raw.get("image_path") or ""),
                    text_paths=list(raw.get("text_paths") or []),
                    issue=str(raw.get("issue") or ""),
                    severity=str(raw.get("severity") or ""),
                ),
            )

    meta_points: list[str] = []
    target_journal = ""
    for block in data.get("metadata_notes") or []:
        if not isinstance(block, dict):
            continue
        for point in block.get("key_points") or []:
            s = str(point)
            meta_points.append(s)
            if "target_journal:" in s.lower():
                target_journal = s.split(":", 1)[-1].strip()

    return ManuscriptContext(
        summary=str(data.get("summary") or "").strip(),
        target_journal=target_journal,
        mismatch_flags=flags,
        metadata_key_points=meta_points,
    )


def load_manuscript_context_from_execution(execution_dir: Path) -> ManuscriptContext | None:
    final_path = execution_dir / "04_final_standardized.json"
    if not final_path.is_file():
        return None
    from .paper_goal import load_final_standardized

    return manuscript_context_from_standardized(load_final_standardized(final_path))
