from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PaperSection(str, Enum):
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    RELATED_WORK = "related_work"
    METHODOLOGY = "methodology"
    EXPERIMENTS = "experiments"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    REFERENCES = "references"


@dataclass(slots=True)
class ResearchInput:
    """Bundled inputs for the paper pipeline (aligned with input folder layout)."""

    description: str
    details: str
    technical_details: str = ""
    extra_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SectionDraft:
    section: PaperSection
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaperDraft:
    title: str
    sections: list[SectionDraft]
    raw_research_summary: str = ""
    peer_review_notes: str = ""
    validation_report: str = ""
