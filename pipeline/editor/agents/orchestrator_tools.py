"""OpenAI function-calling tools for the EditorOrchestratorAgent."""

from __future__ import annotations

from typing import Any

from pipeline.research.task_kinds import (
    RESULTS_FORBIDDEN_KINDS,
    section_allows_kind,
)

from ..schemas import EditorPlan, FigureSpec, IeeeFormat, SectionSpec

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI Responses API format)
# ---------------------------------------------------------------------------

EDITOR_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_document_goal",
            "description": (
                "Set the article title, IEEE format (conference/journal), and the ordered "
                "list of required section headings for this manuscript."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "article_title": {
                        "type": "string",
                        "description": "Final manuscript title (exact from paper_meta if known).",
                    },
                    "ieee_format": {
                        "type": "string",
                        "enum": ["conference", "journal"],
                        "description": "conference = 4–6 pages; journal = up to ~10 pages.",
                    },
                    "required_sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Ordered list of section headings without Roman numerals, e.g. "
                            "['Abstract', 'Index Terms', 'Introduction', ...]"
                        ),
                        "minItems": 4,
                    },
                },
                "required": ["article_title", "ieee_format", "required_sections"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "map_section_sources",
            "description": (
                "For one section heading, specify which trusted research artifact slugs "
                "and which manuscript parts (e.g. 'summary', 'experimental_design', "
                "'methods_text') should feed the section writer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "Short ID, e.g. 'introduction', 'methods', 'discussion'.",
                    },
                    "heading": {
                        "type": "string",
                        "description": "Full heading as it appears in the outline.",
                    },
                    "order": {
                        "type": "integer",
                        "description": "Position in document (1-indexed).",
                    },
                    "research_slugs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Slug strings from 06_research/ that feed this section.",
                    },
                    "manuscript_parts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Keys: 'summary', 'key_claims', 'experimental_design', "
                            "'methods_text', 'mismatch_flags', 'source_text_blocks' "
                            "(all 04 text_blocks), or 'source_text:<path_fragment>' "
                            "(e.g. source_text:overview, source_text:method). "
                            "Writers always receive full 04 source in primary_manuscript_source; "
                            "these keys add section-focused slices."
                        ),
                    },
                    "notes": {
                        "type": "string",
                        "description": (
                            "Rare extra instructions for the section writer only when "
                            "something cannot be expressed via slugs or manuscript_parts."
                        ),
                    },
                },
                "required": ["section_id", "heading", "order"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_research_slug",
            "description": (
                "Assign one trusted research slug to exactly one section. "
                "Call once per slug in the Research catalog after map_section_sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "Target section_id (must exist from map_section_sources).",
                    },
                    "slug": {
                        "type": "string",
                        "description": "Research artifact slug from the catalog.",
                    },
                },
                "required": ["section_id", "slug"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_figure",
            "description": (
                "Register a figure to be generated. Provide a unique figure_id, "
                "the intended caption, what the figure should show, and data hints "
                "from key_claims (quantitative values to encode). "
                "If an existing image can be reused, set reuse_path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "figure_id": {
                        "type": "string",
                        "description": "Short ID, e.g. 'fig1_snr_comparison'.",
                    },
                    "caption": {
                        "type": "string",
                        "description": "IEEE-style figure caption.",
                    },
                    "intent": {
                        "type": "string",
                        "description": "What the figure should visually communicate.",
                    },
                    "data_hints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Quantitative values from key_claims to encode.",
                    },
                    "reuse_path": {
                        "type": "string",
                        "description": (
                            "Relative path to an existing image to reuse as-is "
                            "(e.g. 'images/image1.png'). Leave empty to generate new."
                        ),
                    },
                    "order": {
                        "type": "integer",
                        "description": "Figure number (1-indexed).",
                        "default": 1,
                    },
                    "primary_sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "section_id values that should introduce this figure in prose "
                            "(e.g. ['results'] or ['results', 'discussion']). "
                            "Other sections may cite \\ref only if needed."
                        ),
                    },
                },
                "required": ["figure_id", "caption", "intent", "primary_sections"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_validation_focus",
            "description": (
                "Specify 1–4 validation focus areas for the IEEE validator "
                "(e.g. citation format, abstract word count, figure references)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 4,
                    },
                },
                "required": ["focus_areas"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_editor_plan",
            "description": "Seal the editor plan. Call this last, after all sections and figures are mapped.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ready": {
                        "type": "boolean",
                        "description": "Must be true to finalize.",
                    },
                },
                "required": ["ready"],
                "additionalProperties": False,
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Plan builder (mutated by tool handlers, mirroring OrchestratorPlanBuilder)
# ---------------------------------------------------------------------------


class EditorPlanBuilder:
    def __init__(
        self,
        *,
        trusted_slugs: frozenset[str] | None = None,
        slug_kinds: dict[str, str] | None = None,
    ) -> None:
        self.article_title: str = ""
        self.ieee_format: IeeeFormat = "journal"
        self.required_sections: list[str] = []
        self.section_specs: list[SectionSpec] = []
        self.figure_specs: list[FigureSpec] = []
        self.validation_focus: list[str] = []
        self._finalized: bool = False
        self._trusted_slugs = trusted_slugs or frozenset()
        self._slug_kinds = slug_kinds or {}
        self._slug_to_section: dict[str, str] = {}

    def _slug_section_error(self, slug: str, section_id: str) -> str | None:
        kind = self._slug_kinds.get(slug, "unknown")
        if section_id == "results" and kind in RESULTS_FORBIDDEN_KINDS:
            return (
                f"Slug {slug!r} (task_kind={kind}) cannot feed Results — "
                "literature/benchmark data is not this study's measured outcome."
            )
        if not section_allows_kind(section_id, kind):  # type: ignore[arg-type]
            return (
                f"Slug {slug!r} (task_kind={kind}) cannot be assigned to section "
                f"{section_id!r}. Use allowed_sections from the catalog."
            )
        return None

    def is_complete(self) -> bool:
        return (
            self._finalized
            and bool(self.article_title)
            and bool(self.section_specs)
        )

    def to_plan(self) -> EditorPlan:
        return EditorPlan(
            ieee_format=self.ieee_format,
            article_title=self.article_title,
            sections=self.section_specs,
            figures=self.figure_specs,
            validation_focus=self.validation_focus,
        )

    def tool_handlers(self) -> dict[str, Any]:
        return {
            "set_document_goal": self._set_document_goal,
            "map_section_sources": self._map_section_sources,
            "assign_research_slug": self._assign_research_slug,
            "delegate_figure": self._delegate_figure,
            "set_validation_focus": self._set_validation_focus,
            "finalize_editor_plan": self._finalize_editor_plan,
        }

    def _section_by_id(self, section_id: str) -> SectionSpec | None:
        for spec in self.section_specs:
            if spec.section_id == section_id:
                return spec
        return None

    def _unassigned_slugs(self) -> list[str]:
        return sorted(self._trusted_slugs - set(self._slug_to_section))

    # --- handlers ---

    def _set_document_goal(
        self,
        *,
        article_title: str,
        ieee_format: str = "journal",
        required_sections: list[str] | None = None,
    ) -> dict[str, str]:
        self.article_title = article_title
        self.ieee_format = "conference" if ieee_format == "conference" else "journal"
        self.required_sections = list(required_sections or [])
        return {"status": "ok", "message": f"Goal set: {article_title}"}

    def _map_section_sources(
        self,
        *,
        section_id: str,
        heading: str,
        order: int = 1,
        research_slugs: list[str] | None = None,
        manuscript_parts: list[str] | None = None,
        notes: str = "",
        **_: Any,
    ) -> dict[str, str]:
        if not section_id or not heading:
            return {"status": "error", "message": "section_id and heading are required."}
        if self._section_by_id(section_id) is not None:
            return {
                "status": "error",
                "message": f"Section {section_id!r} already mapped. Use assign_research_slug to add slugs.",
            }
        slugs = list(research_slugs or [])
        for slug in slugs:
            sec_err = self._slug_section_error(slug, section_id)
            if sec_err:
                return {"status": "error", "message": sec_err}
            if self._trusted_slugs and slug not in self._trusted_slugs:
                return {
                    "status": "error",
                    "message": f"Unknown or untrusted slug: {slug}",
                }
            if slug in self._slug_to_section:
                return {
                    "status": "error",
                    "message": (
                        f"Slug {slug!r} already assigned to section "
                        f"{self._slug_to_section[slug]!r}. Each slug → one section only."
                    ),
                }
        for slug in slugs:
            self._slug_to_section[slug] = section_id
        spec = SectionSpec(
            section_id=section_id,
            heading=heading,
            order=order,
            research_slugs=slugs,
            manuscript_parts=list(manuscript_parts or []),
            notes=notes,
        )
        self.section_specs.append(spec)
        return {"status": "ok", "message": f"Section '{heading}' mapped (order {order})."}

    def _assign_research_slug(
        self,
        *,
        section_id: str,
        slug: str,
        **_: Any,
    ) -> dict[str, str]:
        if not section_id or not slug:
            return {"status": "error", "message": "section_id and slug are required."}
        if self._trusted_slugs and slug not in self._trusted_slugs:
            return {"status": "error", "message": f"Unknown or untrusted slug: {slug}"}
        sec_err = self._slug_section_error(slug, section_id)
        if sec_err:
            return {"status": "error", "message": sec_err}
        if slug in self._slug_to_section:
            return {
                "status": "error",
                "message": (
                    f"Slug {slug!r} already assigned to {self._slug_to_section[slug]!r}."
                ),
            }
        spec = self._section_by_id(section_id)
        if spec is None:
            return {
                "status": "error",
                "message": f"Unknown section_id {section_id!r}. Call map_section_sources first.",
            }
        spec.research_slugs.append(slug)
        self._slug_to_section[slug] = section_id
        return {
            "status": "ok",
            "message": f"Assigned {slug!r} → {section_id}.",
        }

    def _delegate_figure(
        self,
        *,
        figure_id: str,
        caption: str,
        intent: str,
        data_hints: list[str] | None = None,
        reuse_path: str = "",
        order: int = 1,
        primary_sections: list[str] | None = None,
        **__: Any,
    ) -> dict[str, str]:
        if not figure_id:
            return {"status": "error", "message": "figure_id is required."}
        primaries = list(primary_sections or [])
        if not primaries:
            return {
                "status": "error",
                "message": "primary_sections is required (non-empty list of section_id values).",
            }
        spec = FigureSpec(
            figure_id=figure_id,
            caption=caption,
            intent=intent,
            data_hints=list(data_hints or []),
            reuse_path=reuse_path,
            order=order,
            primary_sections=primaries,
        )
        self.figure_specs.append(spec)
        return {"status": "ok", "message": f"Figure '{figure_id}' registered."}

    def _set_validation_focus(
        self,
        *,
        focus_areas: list[str],
    ) -> dict[str, str]:
        self.validation_focus = list(focus_areas)
        return {"status": "ok", "message": f"{len(focus_areas)} validation focus areas set."}

    def _finalize_editor_plan(self, *, ready: bool = True) -> dict[str, str]:
        if not ready:
            return {"status": "error", "message": "Set ready=true to finalize."}
        if not self.article_title:
            return {"status": "error", "message": "Call set_document_goal first."}
        if not self.section_specs:
            return {"status": "error", "message": "Map at least one section before finalizing."}
        missing = self._unassigned_slugs()
        if missing:
            return {
                "status": "error",
                "message": (
                    "Unassigned trusted slugs: "
                    + ", ".join(missing)
                    + ". Call assign_research_slug once per slug, then finalize again."
                ),
            }
        self._finalized = True
        return {
            "status": "ok",
            "message": (
                f"Plan finalized: {len(self.section_specs)} sections, "
                f"{len(self.figure_specs)} figures."
            ),
        }
