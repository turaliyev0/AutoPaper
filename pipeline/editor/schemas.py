"""Pydantic models for the editor pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums / literals
# ---------------------------------------------------------------------------

IeeeFormat = Literal["conference", "journal"]

SectionId = Literal[
    "abstract",
    "index_terms",
    "introduction",
    "background",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "references",
    "custom",
]


# ---------------------------------------------------------------------------
# Plan models (produced by the editor orchestrator)
# ---------------------------------------------------------------------------


class SectionSpec(BaseModel):
    """One IEEE section as planned by the orchestrator."""

    section_id: str
    heading: str
    order: int
    research_slugs: list[str] = Field(default_factory=list)
    manuscript_parts: list[str] = Field(
        default_factory=list,
        description=(
            "Manuscript slices for writers: summary, key_claims, experimental_design, "
            "methods_text, mismatch_flags, source_text_blocks, source_text:<path_fragment>."
        ),
    )
    max_words: int = Field(
        default=0,
        description="Legacy; 0 means no orchestrator word cap (writers choose length).",
    )
    notes: str = ""
    available_figure_ids: list[dict] = Field(
        default_factory=list,
        description="Injected by SectionCoordinator: [{figure_id, caption}] for cross-references.",
    )


class FigureSpec(BaseModel):
    """One figure as planned by the orchestrator."""

    figure_id: str
    caption: str
    intent: str
    data_hints: list[str] = Field(
        default_factory=list,
        description="Quantitative values from key_claims to encode in the figure.",
    )
    reuse_path: str = ""
    order: int = 0
    primary_sections: list[str] = Field(
        default_factory=list,
        description=(
            "section_id values that should introduce this figure (e.g. ['results']). "
            "Empty = any section may reference."
        ),
    )


class EditorPlan(BaseModel):
    """Sealed plan produced by EditorOrchestratorAgent → written to 09_editor_plan.json."""

    ieee_format: IeeeFormat = "journal"
    article_title: str = ""
    sections: list[SectionSpec] = Field(default_factory=list)
    figures: list[FigureSpec] = Field(default_factory=list)
    validation_focus: list[str] = Field(default_factory=list)
    raw_tool_state: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def ordered_sections(self) -> list[SectionSpec]:
        return sorted(self.sections, key=lambda s: s.order)


# ---------------------------------------------------------------------------
# Section drafts (produced by SectionWriterAgent)
# ---------------------------------------------------------------------------


class CitationEntry(BaseModel):
    """One bibliography entry in the manuscript citation pool."""

    citekey: str = ""
    authors: str = ""
    year: int | str = ""
    title: str = ""
    journal: str = ""
    doi: str = ""

    def bibtex_line(self) -> str:
        from .bibtex_utils import normalize_bibtex_authors

        author_field = normalize_bibtex_authors(self.authors)
        lines = [
            f"@article{{{self.citekey},",
            f"  author  = {{{author_field}}},",
            f"  title   = {{{self.title}}},",
            f"  journal = {{{self.journal}}},",
            f"  year    = {{{self.year}}},",
        ]
        doi = str(self.doi or "").strip()
        if doi:
            lines.append(f"  doi     = {{{doi}}},")
        lines.append("}")
        return "\n".join(lines)


class SectionDraft(BaseModel):
    """Draft of one IEEE section produced by SectionWriterAgent."""

    section_id: str
    heading: str
    latex_body: str = ""
    citations_used: list[str] = Field(
        default_factory=list,
        description="Citekeys from citation_pool referenced in latex_body.",
    )
    figures_referenced: list[str] = Field(default_factory=list)
    word_count: int = 0
    agent_id: str = "section_writer"
    success: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# Figure results (produced by FigureAgent)
# ---------------------------------------------------------------------------


class FigureResult(BaseModel):
    """Output of FigureAgent for one figure spec."""

    figure_id: str
    output_path: str = ""
    code_path: str = ""
    success: bool = False
    retries: int = 0
    error: str | None = None
    validation_notes: str = ""


# ---------------------------------------------------------------------------
# Editor validation (produced by IeeeValidatorAgent)
# ---------------------------------------------------------------------------


class EditorValidationResult(BaseModel):
    """Verdict for one section or the whole document."""

    section_id: str
    verdict: Literal["pass", "warn", "fail"] = "pass"
    score: int = 100
    issues: list[str] = Field(default_factory=list)
    notes: str = ""
    rewrite_attempts: int = 0
    validated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def needs_rewrite(self, *, threshold: int) -> bool:
        return self.verdict == "fail" or self.score < threshold


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


class EditorRunResult(BaseModel):
    """Top-level result returned by EditorPipeline.run()."""

    plan: EditorPlan | None = None
    sections: list[SectionDraft] = Field(default_factory=list)
    figures: list[FigureResult] = Field(default_factory=list)
    validation: list[EditorValidationResult] = Field(default_factory=list)
    manuscript_tex: str = ""
    pdf_path: str = ""
    errors: list[str] = Field(default_factory=list)
    completed_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def successful_sections(self) -> list[SectionDraft]:
        return [s for s in self.sections if s.success]

    @property
    def failed_sections(self) -> list[SectionDraft]:
        return [s for s in self.sections if not s.success]

    @property
    def successful_figures(self) -> list[FigureResult]:
        return [f for f in self.figures if f.success]
