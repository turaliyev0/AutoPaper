"""Post-orchestrator plan enrichment (synthetic figures from manuscript results)."""

from __future__ import annotations

import logging
import re

from .context import EditorContext
from .manuscript_metrics import has_measured_outcomes as _has_measured_outcomes
from .schemas import EditorPlan, FigureSpec

logger = logging.getLogger(__name__)

_RESULTS_MARKERS = re.compile(
    r"results summary|impedance \(flexible\)|baseline \d+\s*k|gfap flexible|"
    r"units retained|p\s*<\s*0\.001",
    re.IGNORECASE,
)

_METRIC_LINE = re.compile(
    r"impedance|snr|signal-to-noise|gfap|iba1|spike|neuron|khz|kω|kohm|"
    r"\d+\s*week|p\s*<|anova|expected outcome|evaluation metrics",
    re.IGNORECASE,
)


def _manuscript_text_blob(manuscript) -> str:
    chunks: list[str] = [manuscript.summary or ""]
    for block in manuscript.text_blocks:
        chunks.append(str(block.get("technical_analysis") or ""))
    return "\n".join(chunks)


def _manuscript_has_results(manuscript) -> bool:
    """True when step-04 includes reported outcomes or plottable measured metrics."""
    if hasattr(manuscript, "has_measured_outcomes") and manuscript.has_measured_outcomes():
        return True
    if _RESULTS_MARKERS.search(_manuscript_text_blob(manuscript)):
        return True
    return bool(_collect_data_hints(manuscript))


def _collect_data_hints(manuscript) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()

    def _add_line(raw: str) -> None:
        line = raw.strip().lstrip("-").strip()
        if not line or not _METRIC_LINE.search(line):
            return
        key = line.lower()
        if key in seen:
            return
        seen.add(key)
        hints.append(line[:200])

    for block in manuscript.text_blocks:
        for line in str(block.get("technical_analysis") or "").splitlines():
            _add_line(line)
    if len(hints) < 4:
        for line in (manuscript.summary or "").splitlines():
            _add_line(line)
    return hints[:12]


def enrich_editor_plan(plan: EditorPlan, context: EditorContext) -> EditorPlan:
    """
    Add or complete synthetic matplotlib figures when the manuscript includes
    quantitative results (typical when no usable uploaded images exist).
    """
    if not _manuscript_has_results(context.manuscript):
        if plan.figures and not context.manuscript.usable_images():
            before = len(plan.figures)
            plan.figures = [
                f
                for f in plan.figures
                if (f.reuse_path or "").strip() or f.data_hints
            ]
            if before - len(plan.figures):
                logger.info(
                    "Dropped %d figure(s): no quantitative manuscript data for synthetic plots",
                    before - len(plan.figures),
                )
        return plan

    hints = _collect_data_hints(context.manuscript)
    if not hints:
        return plan

    updated_figures: list[FigureSpec] = []
    for fig in plan.figures:
        if not (fig.reuse_path or "").strip() and not fig.data_hints:
            fig = fig.model_copy(update={"data_hints": hints[:8]})
        updated_figures.append(fig)
    plan.figures = updated_figures

    if plan.figures:
        logger.info(
            "Enriched %d figure(s) with manuscript data_hints",
            sum(1 for f in plan.figures if f.data_hints),
        )
    else:
        logger.info(
            "Enriching editor plan with synthetic results figures (%d data hints)",
            len(hints),
        )
        plan.figures = [
        FigureSpec(
            figure_id="fig_impedance_timeline",
            caption=(
                "Chronic electrode impedance at 1 kHz for flexible polyimide and rigid "
                "silicon probes over the chronic implantation period (mean ± SD)."
            ),
            intent="Line plot: impedance (kΩ) vs week for flexible vs rigid groups.",
            data_hints=[
                h for h in hints
                if "impedance" in h.lower() or "kω" in h.lower() or "kohm" in h.lower()
            ] or hints[:4],
            order=1,
            primary_sections=["results"],
        ),
        FigureSpec(
            figure_id="fig_histology_bars",
            caption=(
                "Normalized GFAP and Iba1 fluorescence intensity for flexible vs rigid "
                "electrode groups relative to unimplanted control (1.00)."
            ),
            intent="Grouped bar chart: GFAP and Iba1 for flexible, rigid, and control.",
            data_hints=[
                h for h in hints
                if "gfap" in h.lower() or "iba1" in h.lower()
            ] or hints[-4:],
            order=2,
            primary_sections=["results"],
        ),
        ]

    if not context.manuscript.usable_images():
        before = len(plan.figures)
        plan.figures = [
            f
            for f in plan.figures
            if (f.reuse_path or "").strip() or f.data_hints
        ]
        dropped = before - len(plan.figures)
        if dropped:
            logger.info(
                "Dropped %d figure(s) after enrichment: no reuse_path or data_hints",
                dropped,
            )

    return plan
