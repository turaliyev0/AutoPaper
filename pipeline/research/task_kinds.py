"""Classify research subtasks for editor slug assignment and provenance checks."""

from __future__ import annotations

import re
from typing import Literal

TaskKind = Literal[
    "literature_review",
    "comparable_studies",
    "methods_context",
    "design_critique",
    "literature_benchmark",
    "mismatch_review",
    "gap_fill",
    "unknown",
]

DataProvenance = Literal[
    "literature_only",
    "manuscript_only",
    "mixed",
    "unknown",
]

# Slugs with these kinds must NEVER feed the Results section (own-study findings only).
RESULTS_FORBIDDEN_KINDS: frozenset[TaskKind] = frozenset({
    "literature_review",
    "literature_benchmark",
    "comparable_studies",
    "mismatch_review",
})

ALLOWED_SECTIONS: dict[TaskKind, frozenset[str]] = {
    "literature_review": frozenset({"introduction", "background"}),
    "comparable_studies": frozenset({"background", "discussion"}),
    "methods_context": frozenset({"materials_and_methods", "discussion"}),
    "design_critique": frozenset({"discussion", "materials_and_methods"}),
    "literature_benchmark": frozenset({"background", "discussion"}),
    "mismatch_review": frozenset({"discussion"}),
    "gap_fill": frozenset({
        "introduction",
        "background",
        "materials_and_methods",
        "discussion",
    }),
    "unknown": frozenset({
        "introduction",
        "background",
        "materials_and_methods",
        "results",
        "discussion",
        "conclusion",
    }),
}

_KIND_LABELS: dict[TaskKind, str] = {
    "literature_review": "Literature review (external sources)",
    "comparable_studies": "Comparable prior studies (external)",
    "methods_context": "Methods / materials contextualization",
    "design_critique": "Experimental design critique",
    "literature_benchmark": "Literature benchmark (NOT this study's measured data)",
    "mismatch_review": "Figure–text mismatch review",
    "gap_fill": "Gap-filling follow-up research",
    "unknown": "General research",
}


def classify_task(task: str) -> TaskKind:
    """Heuristic classification from orchestrator subtask wording."""
    t = task.lower()
    if "grounding in literature is optional" in t or re.search(
        r"figure[\s\-–]*text\s+mismatch", t
    ):
        return "mismatch_review"
    if "quantitative benchmark" in t or "benchmark analysis" in t or (
        "benchmark" in t and "key performance" in t
    ):
        return "literature_benchmark"
    if "literature review" in t or ("literature" in t and "review" in t):
        return "literature_review"
    if "comparable stud" in t or "prior stud" in t and "compar" in t:
        return "comparable_studies"
    if "experimental design" in t or "critique the experimental" in t or (
        "critique" in t and "design" in t
    ):
        return "design_critique"
    if (
        "methods and materials" in t
        or "contextualize the methods" in t
        or "materials contextual" in t
    ):
        return "methods_context"
    if "address the gap" in t or "gap that" in t or "follow-up" in t:
        return "gap_fill"
    return "unknown"


def provenance_for_kind(kind: TaskKind) -> DataProvenance:
    if kind in ("literature_review", "literature_benchmark", "comparable_studies"):
        return "literature_only"
    if kind == "mismatch_review":
        return "manuscript_only"
    if kind in ("methods_context", "design_critique", "gap_fill"):
        return "mixed"
    return "unknown"


def kind_label(kind: TaskKind) -> str:
    return _KIND_LABELS.get(kind, kind)


def section_allows_kind(section_id: str, kind: TaskKind) -> bool:
    return section_id in ALLOWED_SECTIONS.get(kind, ALLOWED_SECTIONS["unknown"])
