"""Strict editor plan validation (no auto-repair or fallbacks)."""

from __future__ import annotations

import re

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
