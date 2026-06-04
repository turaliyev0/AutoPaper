"""Holistic manuscript QA — one review pass over all sections and figures."""

from __future__ import annotations

import json
import logging
from typing import Any

from pipeline.research.clients.evaluator_client import JsonLlmClient

from ..context import EditorContext
from ..manuscript_qa_deterministic import build_manuscript_qa_report
from ..prompts.loader import load_manuscript_validator_instruction
from ..schemas import (
    EditorPlan,
    FigureResult,
    FigureRevisionAction,
    ManuscriptQaReport,
    SectionDraft,
    SectionRevisionAction,
)

logger = logging.getLogger(__name__)

AGENT_ID = "manuscript_qa"


def _preview(text: str, limit: int = 2200) -> str:
    t = text.strip()
    return t if len(t) <= limit else t[: limit - 3] + "..."


def _build_holistic_payload(
    plan: EditorPlan,
    sections: list[SectionDraft],
    context: EditorContext,
    figures: list[FigureResult],
) -> str:
    fig_by_id = {f.figure_id: f for f in figures}
    figure_specs = []
    for spec in plan.figures:
        fr = fig_by_id.get(spec.figure_id)
        figure_specs.append(
            {
                "figure_id": spec.figure_id,
                "caption": spec.caption[:300],
                "intent": spec.intent[:200],
                "data_hints": spec.data_hints[:8],
                "primary_sections": spec.primary_sections,
                "reuse_path": spec.reuse_path or "",
                "generated_ok": bool(fr and fr.success),
            }
        )

    section_previews = []
    for draft in sorted(sections, key=lambda d: d.section_id):
        spec = next((s for s in plan.sections if s.section_id == draft.section_id), None)
        section_previews.append(
            {
                "section_id": draft.section_id,
                "heading": draft.heading,
                "word_count": draft.word_count,
                "citations_used": draft.citations_used[:20],
                "figures_referenced": draft.figures_referenced,
                "research_slugs": (spec.research_slugs if spec else [])[:8],
                "latex_body_preview": _preview(draft.latex_body),
            }
        )

    payload: dict[str, Any] = {
        "article_title": context.title,
        "ieee_format": plan.ieee_format,
        "validation_focus": plan.validation_focus,
        "has_measured_outcomes": context.manuscript.has_measured_outcomes(),
        "quantitative_evidence": context.manuscript.quantitative_outcome_lines()[:16],
        "key_claims": context.manuscript.key_claims[:12],
        "mismatch_flags": [
            {"image": f.get("image_path"), "issue": f.get("issue")}
            for f in context.manuscript.mismatch_flags
        ],
        "sections": section_previews,
        "figure_specs": figure_specs,
        "section_plan": [
            {
                "section_id": s.section_id,
                "heading": s.heading,
                "manuscript_parts": s.manuscript_parts,
                "research_slugs": s.research_slugs,
            }
            for s in plan.ordered_sections
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _parse_llm_report(data: dict[str, Any]) -> ManuscriptQaReport:
    section_actions: list[SectionRevisionAction] = []
    for raw in data.get("section_revisions") or []:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("section_id") or "").strip()
        if not sid:
            continue
        sev = str(raw.get("severity") or "major").lower()
        if sev not in ("critical", "major", "minor"):
            sev = "major"
        issues = [str(i).strip() for i in (raw.get("issues") or []) if str(i).strip()]
        if not issues:
            continue
        section_actions.append(
            SectionRevisionAction(
                section_id=sid,
                severity=sev,  # type: ignore[arg-type]
                issues=issues,
                coordination_notes=str(raw.get("coordination_notes") or "").strip(),
            )
        )

    figure_actions: list[FigureRevisionAction] = []
    for raw in data.get("figure_revisions") or []:
        if not isinstance(raw, dict):
            continue
        fid = str(raw.get("figure_id") or "").strip()
        if not fid:
            continue
        issues = [str(i).strip() for i in (raw.get("issues") or []) if str(i).strip()]
        if not issues:
            continue
        figure_actions.append(FigureRevisionAction(figure_id=fid, issues=issues))

    verdict = str(data.get("verdict") or "warn").lower()
    if verdict not in ("pass", "warn", "fail"):
        verdict = "warn"
    score_raw = data.get("score")
    score = int(score_raw) if isinstance(score_raw, (int, float)) else 70
    score = max(0, min(100, score))

    doc_issues = [
        str(i).strip() for i in (data.get("document_issues") or []) if str(i).strip()
    ]
    return ManuscriptQaReport(
        verdict=verdict,  # type: ignore[arg-type]
        score=score,
        document_issues=doc_issues,
        section_actions=section_actions,
        figure_actions=figure_actions,
        notes=str(data.get("notes") or "").strip(),
    )


class ManuscriptQaAgent:
    """Reviews the full draft in one pass; merges LLM output with deterministic checks."""

    def __init__(self, client: JsonLlmClient) -> None:
        self._client = client
        self._system = load_manuscript_validator_instruction()

    async def review_manuscript(
        self,
        plan: EditorPlan,
        sections: list[SectionDraft],
        context: EditorContext,
        figures: list[FigureResult],
        *,
        revision_round: int = 0,
        use_llm: bool = True,
    ) -> ManuscriptQaReport:
        llm_report: ManuscriptQaReport | None = None
        if use_llm and sections:
            user = _build_holistic_payload(plan, sections, context, figures)
            try:
                data = await self._client.generate_json(
                    system=self._system,
                    user=user,
                    trace_label=f"manuscript_qa:round_{revision_round}",
                )
                llm_report = _parse_llm_report(data)
            except Exception as exc:
                logger.warning("Manuscript QA LLM failed: %s", exc)
                llm_report = ManuscriptQaReport(
                    verdict="warn",
                    score=60,
                    document_issues=[f"Holistic LLM review failed: {exc}"],
                    notes="Deterministic checks only.",
                )

        return build_manuscript_qa_report(
            plan,
            sections,
            context,
            figures,
            llm_report=llm_report,
            revision_round=revision_round,
        )
