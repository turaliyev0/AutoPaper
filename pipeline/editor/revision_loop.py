"""Integrated editor QA loop — orchestrator output, figures, and validator work together."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from backend.logging.editor_run import RunLog

from .agents.figure_agent import FigureAgent
from .agents.manuscript_qa import ManuscriptQaAgent
from .agents.section_writer import SectionWriterAgent
from .config import EditorSettings
from .context import EditorContext
from .manuscript_qa_deterministic import qa_report_to_section_validation
from .schemas import (
    EditorPlan,
    EditorValidationResult,
    FigureResult,
    ManuscriptQaReport,
    SectionDraft,
    SectionRevisionAction,
)

logger = logging.getLogger(__name__)

EXEC_QA_REPORT = "12_editor_validation/manuscript_qa_report.json"


def _peer_section_excerpts(
    sections: list[SectionDraft],
    exclude_id: str,
    *,
    limit: int = 700,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for draft in sections:
        if draft.section_id == exclude_id or not draft.latex_body.strip():
            continue
        body = draft.latex_body.strip()
        out[draft.section_id] = body if len(body) <= limit else body[: limit - 3] + "..."
    return out


def _figure_specs_payload(plan: EditorPlan, figures: list[FigureResult]) -> list[dict[str, Any]]:
    fig_by_id = {f.figure_id: f for f in figures}
    payload: list[dict[str, Any]] = []
    for spec in plan.figures:
        fr = fig_by_id.get(spec.figure_id)
        payload.append(
            {
                "figure_id": spec.figure_id,
                "caption": spec.caption,
                "data_hints": spec.data_hints,
                "primary_sections": spec.primary_sections,
                "generated_ok": bool(fr and fr.success),
            }
        )
    return payload


def _write_qa_report(run_dir: Path, report: ManuscriptQaReport) -> None:
    path = run_dir / EXEC_QA_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


async def _apply_figure_revisions(
    plan: EditorPlan,
    figures: list[FigureResult],
    report: ManuscriptQaReport,
    figure_agent: FigureAgent,
    context: EditorContext,
    run_dir: Path,
    log: RunLog,
) -> list[FigureResult]:
    if not report.figure_actions:
        return figures

    spec_by_id = {f.figure_id: f for f in plan.figures}
    fig_by_id = {f.figure_id: f for f in figures}
    action_by_id = {a.figure_id: a for a in report.figure_actions}

    figures_dir = run_dir / "11_figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    updated = list(figures)

    for fig_id, action in action_by_id.items():
        spec = spec_by_id.get(fig_id)
        if spec is None:
            continue
        feedback = (
            "Manuscript QA requires figure revision:\n"
            + "\n".join(f"- {i}" for i in action.issues)
            + "\n\nEnsure plot data matches Results narrative and data_hints."
        )
        log.arrow(f"Regenerating figure {fig_id} (QA feedback)")
        await asyncio.sleep(1.0)
        result = await figure_agent.generate(
            spec,
            figures_dir,
            context,
            qa_feedback=feedback,
        )
        if fig_id in fig_by_id:
            idx = next(i for i, f in enumerate(updated) if f.figure_id == fig_id)
            updated[idx] = result
        else:
            updated.append(result)
        if result.success:
            log.ok(f"{fig_id}: regenerated after QA")
        else:
            log.fail(f"{fig_id}: QA regeneration failed — {(result.error or '')[:80]}")

    return updated


async def _apply_section_revisions(
    plan: EditorPlan,
    sections: list[SectionDraft],
    figures: list[FigureResult],
    report: ManuscriptQaReport,
    writer: SectionWriterAgent,
    context: EditorContext,
) -> list[SectionDraft]:
    if not report.section_actions:
        return sections

    spec_by_id = {s.section_id: s for s in plan.sections}
    draft_by_id = {d.section_id: d for d in sections}
    actions = [
        a
        for a in report.section_actions
        if a.severity in ("critical", "major") or a.issues
    ]

    async def _rewrite_one(action: SectionRevisionAction) -> tuple[str, SectionDraft]:
        spec = spec_by_id.get(action.section_id)
        prior = draft_by_id.get(action.section_id)
        if spec is None or prior is None:
            return action.section_id, prior or SectionDraft(
                section_id=action.section_id,
                heading=action.section_id,
                success=False,
                error="Missing section spec or draft.",
            )
        qa_revision = {
            "mode": "manuscript_qa_revision",
            "document_issues": report.document_issues,
            "section_issues": action.issues,
            "coordination_notes": action.coordination_notes,
            "peer_sections": _peer_section_excerpts(sections, action.section_id),
            "figure_specs": _figure_specs_payload(plan, figures),
            "quantitative_evidence": context.manuscript.quantitative_outcome_lines()[:16],
            "has_measured_outcomes": context.manuscript.has_measured_outcomes(),
            "instruction": (
                "Rewrite this section as part of a coordinated manuscript revision. "
                "Fix every listed issue while keeping consistency with peer_sections. "
                "When Results references a figure, include numeric values aligned with "
                "figure_specs data_hints. Remove pipeline/internal terms."
            ),
        }
        revised = await writer.rewrite_section(
            spec,
            context,
            prior=prior,
            qa_revision=qa_revision,
        )
        return action.section_id, revised

    results = await asyncio.gather(*[_rewrite_one(a) for a in actions], return_exceptions=True)
    for item in results:
        if isinstance(item, BaseException):
            logger.exception("Section QA rewrite failed: %s", item)
            continue
        sid, draft = item
        draft_by_id[sid] = draft

    return [
        draft_by_id.get(
            s.section_id,
            next(d for d in sections if d.section_id == s.section_id),
        )
        for s in plan.ordered_sections
    ]


async def run_integrated_editor_qa(
    *,
    plan: EditorPlan,
    sections: list[SectionDraft],
    figures: list[FigureResult],
    context: EditorContext,
    qa_agent: ManuscriptQaAgent,
    writer: SectionWriterAgent,
    figure_agent: FigureAgent,
    settings: EditorSettings,
    run_dir: Path,
    log: RunLog,
) -> tuple[list[SectionDraft], list[FigureResult], list[EditorValidationResult], ManuscriptQaReport]:
    """
    Holistic QA loop: review whole manuscript → fix figures → fix sections → repeat.

    Replaces per-section validate/rewrite in isolation.
    """
    from .storage import write_figures, write_sections

    threshold = settings.editor_qa_score_threshold
    max_rounds = settings.editor_qa_max_rounds
    current_sections = list(sections)
    current_figures = list(figures)
    last_report = ManuscriptQaReport()

    for round_idx in range(max_rounds):
        log.arrow(f"Manuscript QA round {round_idx + 1}/{max_rounds} (holistic review)")
        report = await qa_agent.review_manuscript(
            plan,
            current_sections,
            context,
            current_figures,
            revision_round=round_idx,
        )
        last_report = report
        _write_qa_report(run_dir, report)

        if not report.needs_revision(threshold=threshold):
            log.ok(
                f"Manuscript QA passed (score={report.score}, verdict={report.verdict})"
            )
            break

        log.warn(
            f"Manuscript QA round {round_idx + 1}: score={report.score}, "
            f"verdict={report.verdict}, "
            f"{len(report.section_actions)} section(s), "
            f"{len(report.figure_actions)} figure(s) to revise"
        )
        if report.document_issues:
            for doc_issue in report.document_issues[:4]:
                log.arrow(doc_issue[:120])

        if round_idx >= max_rounds - 1:
            log.warn("Max QA rounds reached; proceeding with remaining issues.")
            break

        current_figures = await _apply_figure_revisions(
            plan,
            current_figures,
            report,
            figure_agent,
            context,
            run_dir,
            log,
        )
        if current_figures:
            write_figures(run_dir, current_figures)

        current_sections = await _apply_section_revisions(
            plan,
            current_sections,
            current_figures,
            report,
            writer,
            context,
        )
        write_sections(run_dir, current_sections)

        await asyncio.sleep(1.0)

    validation = qa_report_to_section_validation(
        last_report, current_sections, plan, context
    )
    return current_sections, current_figures, validation, last_report
