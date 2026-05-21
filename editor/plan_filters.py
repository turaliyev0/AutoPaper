"""Post-orchestrator plan cleanup (excluded / duplicate image paths)."""

from __future__ import annotations

import logging

from .context import EditorContext
from .schemas import EditorPlan, FigureSpec

logger = logging.getLogger(__name__)


def filter_editor_plan_figures(plan: EditorPlan, context: EditorContext) -> EditorPlan:
    """
    Drop figures that reuse excluded images or duplicate the same reuse_path.

    Prevents unrelated mismatch-flagged photos from appearing in the IEEE manuscript.
    """
    blocked = context.manuscript.excluded_paths()
    kept: list[FigureSpec] = []
    used_reuse: set[str] = set()

    for fig in sorted(plan.figures, key=lambda f: f.order):
        reuse = (fig.reuse_path or "").strip()
        if reuse and reuse in blocked:
            logger.info(
                "Dropping figure %s: reuse_path %r is excluded (%s)",
                fig.figure_id,
                reuse,
                _exclusion_reason(context, reuse),
            )
            continue
        if reuse and reuse in used_reuse:
            logger.info(
                "Dropping figure %s: reuse_path %r already assigned to another figure",
                fig.figure_id,
                reuse,
            )
            continue
        if reuse:
            used_reuse.add(reuse)
        kept.append(fig)

    if len(kept) != len(plan.figures):
        plan.figures = kept
    return plan


def _exclusion_reason(context: EditorContext, path: str) -> str:
    for ex in context.manuscript.excluded_images:
        if ex.get("path") == path:
            return str(ex.get("reason") or "excluded")
    return "excluded"
