"""Pre-assembly academic integrity checks (deterministic)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pipeline.research.task_kinds import RESULTS_FORBIDDEN_KINDS

if TYPE_CHECKING:
    from .context import EditorContext
    from .schemas import EditorPlan, SectionDraft

# Numeric claims in Results without a nearby citation are suspicious.
_NUMERIC = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|kΩ|kOhm|µm|um|mm|Hz|kHz|mV|nA|dB|×|x)\b",
    re.IGNORECASE,
)
_CITE_NEAR = re.compile(r"\\cite\{[^}]+\}")
# KPI / acquisition specs from methods (not reported findings).
_METHOD_SPEC_BEFORE = re.compile(
    r"(?:\bat\b|\bof\b|\bfor\b|\bto\b|\bfrom\b|\bbetween\b|\brange\b|\bthreshold\b|"
    r"\bfilter\b|\brate\b|\bspacing\b|\bthick(?:ness)?\b|\bduration\b|\bweeks?\b)\s*$",
    re.IGNORECASE,
)
_NO_FINDINGS = re.compile(
    r"not provided|cannot be presented|not available|no quantitative|were not|"
    r"is not provided|cannot be|without measured|lack(?:s|ing)? (?:the )?quantitative",
    re.IGNORECASE,
)


def _numeric_is_method_spec(body: str, match: re.Match[str]) -> bool:
    """True when the number is a study-design KPI spec, not a reported measurement."""
    start = max(0, match.start() - 160)
    end = min(len(body), match.end() + 80)
    window = body[start:end]
    prefix = body[start : match.start()]
    if _METHOD_SPEC_BEFORE.search(prefix):
        return True
    if _NO_FINDINGS.search(window):
        return True
    design_phrases = (
        "indicators",
        "evaluated",
        "included",
        "assessed",
        "metrics",
        "performance indicators",
        "key performance",
        "expected",
        "anticipated",
        "hypothesis",
        "objective",
        "aimed to",
    )
    lower = window.lower()
    return any(p in lower for p in design_phrases)


def collect_integrity_errors(
    plan: "EditorPlan",
    sections: list["SectionDraft"],
    context: "EditorContext",
) -> list[str]:
    errors: list[str] = []

    slug_kind = {a.slug: a.task_kind for a in context.trusted_artifacts}
    results_spec = next((s for s in plan.sections if s.section_id == "results"), None)
    if results_spec:
        for slug in results_spec.research_slugs:
            kind = slug_kind.get(slug, "unknown")
            if kind in RESULTS_FORBIDDEN_KINDS:
                errors.append(
                    f"Results section includes slug {slug!r} ({kind}) — "
                    "literature/benchmark slugs are not allowed in Results."
                )

    usable = context.manuscript.usable_images()
    if not usable and plan.figures:
        from .plan_enrichment import _manuscript_has_results

        has_results = _manuscript_has_results(context.manuscript)
        all_synthetic_ok = has_results and all(
            (fig.reuse_path or "").strip() or fig.data_hints for fig in plan.figures
        )
        if not all_synthetic_ok:
            errors.append(
                f"Plan has {len(plan.figures)} figure(s) but no usable manuscript images; "
                "remove figures or provide a valid reuse_path."
            )

    if context.manuscript.excluded_images and plan.figures:
        for fig in plan.figures:
            reuse = (fig.reuse_path or "").strip()
            if reuse and reuse in context.manuscript.excluded_paths():
                errors.append(
                    f"Figure {fig.figure_id!r} reuses excluded image {reuse!r}."
                )

    results_draft = next((d for d in sections if d.section_id == "results"), None)
    if results_draft and results_draft.success and results_draft.latex_body:
        body = results_draft.latex_body
        for match in _NUMERIC.finditer(body):
            if _numeric_is_method_spec(body, match):
                continue
            start = max(0, match.start() - 120)
            window = body[start : match.end() + 40]
            if not _CITE_NEAR.search(window):
                errors.append(
                    "Results section contains numeric values without a nearby "
                    f"\\cite{{}} (e.g. near '{match.group()}'). "
                    "Literature benchmarks must be cited as prior work, not "
                    "presented as this study's measurements."
                )
                break

    return errors


def validate_manuscript_integrity(
    plan: "EditorPlan",
    sections: list["SectionDraft"],
    context: "EditorContext",
) -> None:
    errors = collect_integrity_errors(plan, sections, context)
    if errors:
        raise ValueError(
            "Manuscript integrity check failed:\n- " + "\n- ".join(errors)
        )
