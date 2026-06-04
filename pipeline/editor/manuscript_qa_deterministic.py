"""Deterministic whole-manuscript checks (cross-section + integrity)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .deterministic_checks import (
    deterministic_section_checks,
    flatten_issues,
    result_from_issues,
    _results_has_measurements,
)
from .integrity_check import collect_integrity_errors
from .schemas import (
    EditorPlan,
    EditorValidationResult,
    FigureResult,
    FigureRevisionAction,
    ManuscriptQaReport,
    SectionDraft,
    SectionRevisionAction,
)

if TYPE_CHECKING:
    from .context import EditorContext

_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_PIPELINE_WORDS = re.compile(
    r"\b(autopaper|execution_\d+|search agent|validation run)\b",
    re.IGNORECASE,
)


def _word_set(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: str, b: str) -> float:
    sa, sb = _word_set(a), _word_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _section_map(sections: list[SectionDraft]) -> dict[str, SectionDraft]:
    return {s.section_id: s for s in sections}


def collect_cross_section_actions(
    plan: EditorPlan,
    sections: list[SectionDraft],
    context: "EditorContext",
    figures: list[FigureResult],
) -> tuple[list[SectionRevisionAction], list[FigureRevisionAction], list[str]]:
    """Rule-based manuscript-wide issues the per-section validator cannot see."""
    by_id = _section_map(sections)
    section_actions: list[SectionRevisionAction] = []
    figure_actions: list[FigureRevisionAction] = []
    document_issues: list[str] = []

    fig_ids = {f.figure_id for f in plan.figures}
    fig_by_id = {f.figure_id: f for f in figures}
    spec_by_id = {f.figure_id: f for f in plan.figures}

    for draft in sections:
        if not draft.success:
            continue
        for fid in draft.figures_referenced:
            if fid not in fig_ids:
                msg = (
                    f"Section {draft.section_id!r} references unknown figure {fid!r}. "
                    f"Use only: {sorted(fig_ids)}."
                )
                section_actions.append(
                    SectionRevisionAction(
                        section_id=draft.section_id,
                        severity="critical",
                        issues=[msg],
                        coordination_notes="Align \\ref{fig:...} with available_figure_ids from the editor plan.",
                    )
                )
                document_issues.append(msg)

    results = by_id.get("results")
    abstract = by_id.get("abstract")
    conclusion = by_id.get("conclusion")

    if results and results.success and plan.figures:
        if not _results_has_measurements(results.latex_body):
            hints: list[str] = []
            for spec in plan.figures:
                if "results" in spec.primary_sections and spec.data_hints:
                    hints.extend(spec.data_hints[:4])
            msg = (
                "Results section contains no numeric measurements but the manuscript includes "
                "data figures. Report illustrative values consistent with figure data_hints and "
                "quantitative_evidence; reference each figure introduced in Results."
            )
            section_actions.append(
                SectionRevisionAction(
                    section_id="results",
                    severity="critical",
                    issues=[msg],
                    coordination_notes=(
                        "Use values from figure data_hints when primary_manuscript_source lacks "
                        f"measured outcomes. Hints: {'; '.join(hints[:6]) or 'see figure specs'}."
                    ),
                )
            )
            document_issues.append(msg)

    intro = by_id.get("introduction")
    background = by_id.get("background")
    if intro and background and intro.success and background.success:
        overlap = _jaccard(intro.latex_body[:600], background.latex_body[:600])
        if overlap >= 0.38:
            msg = (
                "Introduction and Background open with overlapping prose. Background must "
                "cover prior literature only — not repeat the clinical motivation paragraph."
            )
            document_issues.append(msg)
            section_actions.append(
                SectionRevisionAction(
                    section_id="background",
                    severity="major",
                    issues=[msg],
                    coordination_notes=(
                        "Read the Introduction excerpt in peer_sections; remove duplicated "
                        "motivation and focus on cited prior work."
                    ),
                )
            )

    if abstract and abstract.success and results and results.success:
        abstract_nums = set(re.findall(r"\d+(?:\.\d+)?", abstract.latex_body))
        results_nums = set(re.findall(r"\d+(?:\.\d+)?", results.latex_body))
        if abstract_nums and not (abstract_nums & results_nums):
            msg = (
                "Abstract cites numeric values that do not appear in Results. "
                "Either add matching measurements to Results or soften Abstract claims."
            )
            document_issues.append(msg)
            section_actions.append(
                SectionRevisionAction(
                    section_id="results",
                    severity="major",
                    issues=[msg],
                    coordination_notes="Mirror key Abstract numerics when reporting findings.",
                )
            )
            section_actions.append(
                SectionRevisionAction(
                    section_id="abstract",
                    severity="minor",
                    issues=[msg],
                    coordination_notes="Ensure Abstract numbers appear in Results or remove them.",
                )
            )

    if conclusion and conclusion.success and results and results.success:
        c_has = bool(re.search(r"\d+(?:\.\d+)?", conclusion.latex_body))
        if c_has and not _results_has_measurements(results.latex_body):
            msg = "Conclusion states numeric outcomes but Results reports none."
            document_issues.append(msg)
            section_actions.append(
                SectionRevisionAction(
                    section_id="results",
                    severity="critical",
                    issues=[msg],
                    coordination_notes="Add the quantitative findings Conclusion summarizes.",
                )
            )

    for draft in sections:
        if draft.success and _PIPELINE_WORDS.search(draft.latex_body):
            match = _PIPELINE_WORDS.search(draft.latex_body)
            term = match.group() if match else "pipeline term"
            msg = f"Pipeline leakage term {term!r} in section {draft.section_id!r}."
            document_issues.append(msg)
            section_actions.append(
                SectionRevisionAction(
                    section_id=draft.section_id,
                    severity="critical",
                    issues=[msg],
                    coordination_notes="Remove internal tooling language from published prose.",
                )
            )

    for spec in plan.figures:
        if "results" not in spec.primary_sections:
            continue
        fr = fig_by_id.get(spec.figure_id)
        if fr and not fr.success:
            msg = f"Figure {spec.figure_id!r} failed generation but Results depends on it."
            document_issues.append(msg)
            figure_actions.append(
                FigureRevisionAction(
                    figure_id=spec.figure_id,
                    issues=[msg, f"Caption: {spec.caption[:200]}"],
                )
            )
        elif results and results.success:
            if spec.figure_id not in results.figures_referenced:
                msg = (
                    f"Figure {spec.figure_id!r} is assigned to Results but not referenced there."
                )
                document_issues.append(msg)
                section_actions.append(
                    SectionRevisionAction(
                        section_id="results",
                        severity="major",
                        issues=[msg],
                        coordination_notes=f"Introduce Fig.~\\ref{{fig:{spec.figure_id}}} with narrative.",
                    )
                )

    return section_actions, figure_actions, document_issues


def merge_section_actions(
    *groups: list[SectionRevisionAction],
) -> list[SectionRevisionAction]:
    """Merge actions for the same section_id."""
    merged: dict[str, SectionRevisionAction] = {}
    rank = {"critical": 3, "major": 2, "minor": 1}
    for group in groups:
        for action in group:
            existing = merged.get(action.section_id)
            if existing is None:
                merged[action.section_id] = action
                continue
            sev = action.severity if rank[action.severity] > rank[existing.severity] else existing.severity
            issues = list(dict.fromkeys(existing.issues + action.issues))
            notes = existing.coordination_notes
            if action.coordination_notes and action.coordination_notes not in notes:
                notes = (notes + " " + action.coordination_notes).strip()
            merged[action.section_id] = SectionRevisionAction(
                section_id=action.section_id,
                severity=sev,
                issues=issues,
                coordination_notes=notes,
            )
    return list(merged.values())


def build_manuscript_qa_report(
    plan: EditorPlan,
    sections: list[SectionDraft],
    context: "EditorContext",
    figures: list[FigureResult],
    *,
    llm_report: ManuscriptQaReport | None = None,
    revision_round: int = 0,
) -> ManuscriptQaReport:
    """Combine integrity, per-section deterministic, cross-section, and optional LLM review."""
    integrity_errors = collect_integrity_errors(plan, sections, context)
    cross_actions, cross_figs, cross_doc = collect_cross_section_actions(
        plan, sections, context, figures
    )

    per_section_actions: list[SectionRevisionAction] = []
    for draft in sections:
        det = deterministic_section_checks(draft, plan, context)
        if not det:
            continue
        flat = flatten_issues(det)
        critical = any(i.get("severity") == "critical" for i in det)
        major = any(i.get("severity") == "major" for i in det)
        sev = "critical" if critical else ("major" if major else "minor")
        per_section_actions.append(
            SectionRevisionAction(
                section_id=draft.section_id,
                severity=sev,  # type: ignore[arg-type]
                issues=flat,
            )
        )

    section_actions = merge_section_actions(per_section_actions, cross_actions)
    if llm_report:
        section_actions = merge_section_actions(section_actions, llm_report.section_actions)
        figure_actions = list({f.figure_id: f for f in cross_figs + llm_report.figure_actions}.values())
        document_issues = list(
            dict.fromkeys(integrity_errors + cross_doc + llm_report.document_issues)
        )
        notes = llm_report.notes
        score = llm_report.score
        verdict = llm_report.verdict
    else:
        figure_actions = cross_figs
        document_issues = list(dict.fromkeys(integrity_errors + cross_doc))
        notes = ""
        score = 100
        verdict = "pass"

    for action in section_actions:
        if action.severity == "critical":
            verdict = "fail"
            score = min(score, 40)
        elif action.severity == "major" and verdict == "pass":
            verdict = "warn"
            score = min(score, 75)

    if integrity_errors:
        verdict = "fail" if verdict != "fail" else verdict
        score = min(score, 50)

    if figure_actions and verdict == "pass":
        verdict = "warn"
        score = min(score, 80)

    return ManuscriptQaReport(
        verdict=verdict,
        score=max(0, score),
        document_issues=document_issues,
        section_actions=section_actions,
        figure_actions=figure_actions,
        notes=notes,
        revision_round=revision_round,
    )


def qa_report_to_section_validation(
    report: ManuscriptQaReport,
    sections: list[SectionDraft],
    plan: EditorPlan,
    context: "EditorContext",
) -> list[EditorValidationResult]:
    """Map holistic QA to per-section artifacts for 12_editor_validation/."""
    action_by_id = {a.section_id: a for a in report.section_actions}
    out: list[EditorValidationResult] = []
    for draft in sections:
        det = deterministic_section_checks(draft, plan, context)
        action = action_by_id.get(draft.section_id)
        extra = list(action.issues) if action else []
        combined = det.copy()
        for msg in extra:
            sev = action.severity if action else "minor"
            combined.append({"severity": sev, "step": "QA", "message": msg})
        result = result_from_issues(
            draft.section_id,
            combined,
            notes=report.notes,
            rewrite_attempts=report.revision_round,
        )
        out.append(result)
    return out
