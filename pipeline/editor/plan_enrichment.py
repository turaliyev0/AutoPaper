"""Post-orchestrator plan enrichment (synthetic figures from manuscript results)."""

from __future__ import annotations

import logging
import re

from .context import EditorContext
from .schemas import EditorPlan, FigureSpec

logger = logging.getLogger(__name__)

_RESULTS_MARKERS = re.compile(
    r"results summary|impedance \(flexible\)|baseline \d+\s*k|gfap flexible|"
    r"units retained|p\s*<\s*0\.001",
    re.IGNORECASE,
)


def _manuscript_has_results(manuscript) -> bool:
    """True when step-04 text includes quantitative outcome lines."""
    chunks: list[str] = [manuscript.summary]
    for block in manuscript.text_blocks:
        chunks.append(str(block.get("technical_analysis") or ""))
    return bool(_RESULTS_MARKERS.search("\n".join(chunks)))


def _collect_data_hints(manuscript) -> list[str]:
    hints: list[str] = []
    for block in manuscript.text_blocks:
        text = str(block.get("technical_analysis") or "")
        if "results summary" in text.lower() or "impedance (flexible)" in text.lower():
            for line in text.splitlines():
                line = line.strip().lstrip("-").strip()
                if line and any(
                    k in line.lower()
                    for k in ("impedance", "snr", "spike", "neuron", "gfap", "iba1", "retained", "p <")
                ):
                    hints.append(line[:200])
    return hints[:12]


def enrich_editor_plan(plan: EditorPlan, context: EditorContext) -> EditorPlan:
    """
    Add or complete synthetic matplotlib figures when the manuscript includes
    quantitative results (typical when no usable uploaded images exist).
    """
    if not _manuscript_has_results(context.manuscript):
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
        return plan

    logger.info("Enriching editor plan with synthetic results figures (%d data hints)", len(hints))

    plan.figures = [
        FigureSpec(
            figure_id="fig_impedance_timeline",
            caption=(
                "Chronic electrode impedance at 1 kHz for flexible polyimide and rigid "
                "silicon probes over 12 weeks (mean ± SD, n=6 per group)."
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
    return plan
