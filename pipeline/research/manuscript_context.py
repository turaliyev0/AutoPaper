"""Structured manuscript context for research steps (from ``04_final_standardized.json``)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pipeline.input.image_registry import active_mismatch_flags

_DESIGN_LINE_KEYWORDS = (
    "hemispher",
    "control design",
    "control group",
    "test group",
    "within-subject",
    "within subject",
    "paired design",
    "implant configuration",
    "subject model",
    "n=",
    "channel count",
    "stereotaxic",
    "utah-style",
    "sprague-dawley",
)


class MismatchFlag(BaseModel):
    image_path: str = ""
    text_paths: list[str] = Field(default_factory=list)
    issue: str = ""
    severity: str = ""


class ManuscriptContext(BaseModel):
    """Passed to orchestrator search agents and the research index builder (research pipeline only)."""

    summary: str = ""
    target_journal: str = ""
    mismatch_flags: list[MismatchFlag] = Field(default_factory=list)
    metadata_key_points: list[str] = Field(default_factory=list)
    experimental_design: list[str] = Field(default_factory=list)
    key_claims: list[str] = Field(default_factory=list)

    def to_orchestrator_block(self) -> str:
        lines: list[str] = []
        if self.target_journal:
            lines.append(f"Target journal: {self.target_journal}")
        if self.experimental_design:
            lines.append(
                "Experimental design (MUST appear in required_outputs, openai_search control-design "
                "task, and final report — do not generalize away):",
            )
            for note in self.experimental_design:
                lines.append(f"  - {note}")
        if self.key_claims:
            lines.append(
                "Key quantitative claims from manuscript (embed into relevant tasks — do not omit):",
            )
            for claim in self.key_claims[:10]:
                lines.append(f"  - {claim}")
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
            "experimental_design": list(self.experimental_design),
            "key_claims": list(self.key_claims),
            "mismatch_flags": [f.model_dump() for f in self.mismatch_flags],
        }


def _dedupe_lines(lines: list[str], *, max_items: int = 14) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line.strip())
        if len(out) >= max_items:
            break
    return out


def extract_experimental_design(data: dict[str, Any]) -> list[str]:
    """Pull method/design bullets from standardized bundle (not only the short summary)."""
    collected: list[str] = []

    for block in data.get("text_blocks") or []:
        if not isinstance(block, dict):
            continue
        path = str(block.get("relative_path") or "").lower()
        text = str(block.get("technical_analysis") or "")
        if not text.strip():
            continue
        is_method_block = any(
            part in path for part in ("method", "detail", "experiment", "procedure")
        )
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("-•* ").strip()
            if len(line) < 12:
                continue
            low = line.lower()
            if any(k in low for k in _DESIGN_LINE_KEYWORDS):
                collected.append(line)
            elif is_method_block and (
                line.endswith(":")
                or low.startswith(("control group", "test group", "subject model"))
            ):
                collected.append(line)

    summary = str(data.get("summary") or "")
    if summary and not any("hemispher" in x.lower() for x in collected):
        for match in re.finditer(
            r"[^.]*\b(hemispher\w*|within[- ]subject|paired)[^.]*\.",
            summary,
            flags=re.IGNORECASE,
        ):
            collected.append(match.group(0).strip())

    return _dedupe_lines(collected)


def manuscript_context_from_standardized(data: dict[str, Any]) -> ManuscriptContext:
    flags: list[MismatchFlag] = []
    for raw in active_mismatch_flags(data):
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

    raw_claims = data.get("key_claims") or []
    key_claims = _dedupe_lines([str(c) for c in raw_claims if isinstance(c, str)], max_items=12)

    return ManuscriptContext(
        summary=str(data.get("summary") or "").strip(),
        target_journal=target_journal,
        mismatch_flags=flags,
        metadata_key_points=meta_points,
        experimental_design=extract_experimental_design(data),
        key_claims=key_claims,
    )


def load_manuscript_context_from_execution(execution_dir: Path) -> ManuscriptContext | None:
    final_path = execution_dir / "04_final_standardized.json"
    if not final_path.is_file():
        return None
    from .paper_goal import load_final_standardized

    return manuscript_context_from_standardized(load_final_standardized(final_path))
