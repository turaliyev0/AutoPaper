"""Strict editor plan validation (no auto-repair or fallbacks)."""

from __future__ import annotations

import re

from pipeline.research.task_kinds import RESULTS_FORBIDDEN_KINDS

from .context import EditorContext
from .schemas import EditorPlan


def collect_plan_validation_errors(
    plan: EditorPlan,
    context: EditorContext,
) -> list[str]:
    """Return plan invariant violations (empty list if valid)."""
    errors: list[str] = []

    slug_owner: dict[str, str] = {}
    assigned: set[str] = set()
    for spec in plan.sections:
        for slug in spec.research_slugs:
            if slug in slug_owner:
                errors.append(
                    f"Duplicate slug {slug!r}: assigned to both "
                    f"{slug_owner[slug]!r} and {spec.section_id!r}"
                )
            else:
                slug_owner[slug] = spec.section_id
            assigned.add(slug)

    trusted = {a.slug for a in context.trusted_artifacts}
    missing = trusted - assigned
    if missing:
        errors.append(
            "Unassigned trusted research slugs: " + ", ".join(sorted(missing))
        )

    unknown = assigned - trusted
    if unknown:
        errors.append(
            "Plan references unknown or untrusted slugs: " + ", ".join(sorted(unknown))
        )

    for fig in plan.figures:
        if not fig.primary_sections:
            errors.append(
                f"Figure {fig.figure_id!r} has no primary_sections "
                "(orchestrator must set this on delegate_figure)"
            )

    slug_kind = {a.slug: a.task_kind for a in context.trusted_artifacts}
    for spec in plan.sections:
        if spec.section_id != "results":
            continue
        for slug in spec.research_slugs:
            kind = slug_kind.get(slug, "unknown")
            if kind in RESULTS_FORBIDDEN_KINDS:
                errors.append(
                    f"Results must not include slug {slug!r} (task_kind={kind}). "
                    "Literature benchmarks belong in Background or Discussion only."
                )

    usable = context.manuscript.usable_images()
    if not usable and plan.figures:
        for fig in plan.figures:
            if not (fig.reuse_path or "").strip():
                errors.append(
                    f"Figure {fig.figure_id!r} has no reuse_path but no usable images exist; "
                    "omit figures or link a valid manuscript image."
                )

    if context.manuscript.excluded_images and plan.figures:
        blocked = context.manuscript.excluded_paths()
        for fig in plan.figures:
            reuse = (fig.reuse_path or "").strip()
            if reuse and reuse in blocked:
                errors.append(
                    f"Figure {fig.figure_id!r} must not reuse excluded path {reuse!r}."
                )

    return errors


def validate_editor_plan(plan: EditorPlan, context: EditorContext) -> None:
    """Fail fast if the orchestrator plan violates supervisor invariants."""
    errors = collect_plan_validation_errors(plan, context)
    if errors:
        raise ValueError(
            "Editor plan validation failed:\n- " + "\n- ".join(errors)
        )


def format_research_index_excerpt(index_md: str, *, char_limit: int = 4500) -> str:
    """Trim research index for orchestrator context (avoid multi-MB blobs)."""
    text = index_md.strip()
    if not text:
        return "(no research index — use Research catalog below)"
    if len(text) <= char_limit:
        return text

    match = re.search(
        r"(# Research Run Catalog.*?)(?:\n## Limitations|\Z)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        chunk = match.group(1).strip()
        if len(chunk) <= char_limit:
            return chunk + "\n\n(index truncated after key sections)"
        return chunk[:char_limit] + "\n\n… (index truncated)"

    return text[:char_limit] + "\n\n… (index truncated)"
