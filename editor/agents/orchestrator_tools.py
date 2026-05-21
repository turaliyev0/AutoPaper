"""OpenAI function-calling tools for the EditorOrchestratorAgent."""

from __future__ import annotations

from typing import Any

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
                            "Ordered list of section headings, e.g. "
                            "['Abstract', 'Index Terms', 'I. Introduction', ...]"
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
                            "Keys like 'summary', 'experimental_design', "
                            "'methods_text', 'key_claims'."
                        ),
                    },
                    "max_words": {
                        "type": "integer",
                        "description": "Target word count for the section body (excluding heading).",
                        "default": 600,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Special instructions for the section writer (optional).",
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
                },
                "required": ["figure_id", "caption", "intent"],
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
    def __init__(self) -> None:
        self.article_title: str = ""
        self.ieee_format: IeeeFormat = "journal"
        self.required_sections: list[str] = []
        self.section_specs: list[SectionSpec] = []
        self.figure_specs: list[FigureSpec] = []
        self.validation_focus: list[str] = []
        self._finalized: bool = False

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
            "delegate_figure": self._delegate_figure,
            "set_validation_focus": self._set_validation_focus,
            "finalize_editor_plan": self._finalize_editor_plan,
        }

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
        max_words: int = 600,
        notes: str = "",
    ) -> dict[str, str]:
        if not section_id or not heading:
            return {"status": "error", "message": "section_id and heading are required."}
        spec = SectionSpec(
            section_id=section_id,
            heading=heading,
            order=order,
            research_slugs=list(research_slugs or []),
            manuscript_parts=list(manuscript_parts or []),
            max_words=max_words,
            notes=notes,
        )
        self.section_specs.append(spec)
        return {"status": "ok", "message": f"Section '{heading}' mapped (order {order})."}

    def _delegate_figure(
        self,
        *,
        figure_id: str,
        caption: str,
        intent: str,
        data_hints: list[str] | None = None,
        reuse_path: str = "",
        order: int = 1,
    ) -> dict[str, str]:
        if not figure_id:
            return {"status": "error", "message": "figure_id is required."}
        spec = FigureSpec(
            figure_id=figure_id,
            caption=caption,
            intent=intent,
            data_hints=list(data_hints or []),
            reuse_path=reuse_path,
            order=order,
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
        self._finalized = True
        return {
            "status": "ok",
            "message": (
                f"Plan finalized: {len(self.section_specs)} sections, "
                f"{len(self.figure_specs)} figures."
            ),
        }
