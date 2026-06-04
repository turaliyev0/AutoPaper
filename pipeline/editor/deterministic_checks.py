"""Shared deterministic section checks for IEEE / manuscript QA."""

from __future__ import annotations

import re
from typing import Any, Literal

from .context import EditorContext
from .schemas import EditorPlan, EditorValidationResult, SectionDraft

StructuredIssue = dict[str, str]

_PIPELINE_WORDS = re.compile(
    r"\b(autopaper|execution_\d+|search agent|validation run)\b",
    re.IGNORECASE,
)
_AUTHOR_YEAR = re.compile(r"\([\w]+\s+et al\.,?\s+\d{4}\)")


def issue(
    severity: Literal["critical", "major", "minor"],
    step: str,
    message: str,
) -> StructuredIssue:
    return {"severity": severity, "step": step, "message": message}


def flatten_issues(raw: list[Any]) -> list[str]:
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            sev = str(item.get("severity") or "").strip()
            step = str(item.get("step") or "").strip()
            msg = str(item.get("message") or "").strip()
            if not msg:
                continue
            prefix = f"[{sev}/{step}]" if sev and step else (f"[{sev}]" if sev else "")
            out.append(f"{prefix} {msg}".strip())
        elif str(item).strip():
            out.append(str(item).strip())
    return out


def score_from_issues(issues: list[StructuredIssue]) -> int:
    score = 100
    for item in issues:
        sev = item.get("severity", "")
        if sev == "critical":
            score -= 30
        elif sev == "major":
            score -= 15
        elif sev == "minor":
            score -= 5
    return max(0, score)


def verdict_from_issues(issues: list[StructuredIssue]) -> Literal["pass", "warn", "fail"]:
    critical = sum(1 for i in issues if i.get("severity") == "critical")
    major = sum(1 for i in issues if i.get("severity") == "major")
    minor = sum(1 for i in issues if i.get("severity") == "minor")
    if critical >= 1 or major >= 2:
        return "fail"
    if major >= 1 or minor >= 3:
        return "warn"
    if minor > 0:
        return "warn"
    return "pass"


_MEASUREMENT_VALUE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|kΩ|kohm|µm|um|mm|hz|khz|mv|na|db)\b|"
    r"\bp\s*[<>=]\s*0?\.\d+\b|"
    r"\bn\s*=\s*\d+\b",
    re.IGNORECASE,
)


def _results_has_measurements(latex: str) -> bool:
    prose = re.sub(r"\\ref\{[^}]+\}", " ", latex)
    prose = re.sub(r"Fig\.~?", " ", prose)
    # Strip design/spec phrases that mention numbers but are not reported findings.
    prose = re.sub(r"\bat\s+\d+(?:\.\d+)?\s*khz\b", " ", prose, flags=re.IGNORECASE)
    prose = re.sub(r"\b\d+\s*-\s*week\b", " ", prose, flags=re.IGNORECASE)
    prose = re.sub(
        r"(?:metrics included|were assessed|evaluation metrics|key performance indicators)",
        " ",
        prose,
        flags=re.IGNORECASE,
    )
    return bool(_MEASUREMENT_VALUE.search(prose))


def deterministic_section_checks(
    draft: SectionDraft,
    plan: EditorPlan,
    context: EditorContext,
) -> list[StructuredIssue]:
    """Fast rule-based checks aligned with IEEE validator v003 STEPs."""
    issues: list[StructuredIssue] = []
    latex = draft.latex_body
    non_ws = len(re.sub(r"\s", "", latex))

    if not latex.strip() or non_ws < 20:
        return [
            issue(
                "critical",
                "STEP 0",
                "Section body is empty or stub. Generation must be re-run.",
            )
        ]

    if draft.section_id == "abstract":
        wc = draft.word_count
        limit = 250 if plan.ieee_format == "journal" else 150
        if wc < 50:
            issues.append(
                issue("critical", "STEP 1", "Abstract is too short to meet IEEE minimum.")
            )
        elif wc > limit:
            issues.append(
                issue(
                    "major",
                    "STEP 1",
                    f"Abstract exceeds IEEE {plan.ieee_format} {limit}-word limit.",
                )
            )

    match = _PIPELINE_WORDS.search(latex)
    if match:
        term = match.group()
        issues.append(
            issue(
                "critical",
                "STEP 4",
                f"Internal pipeline term '{term}' found in manuscript body. "
                "This reveals AI generation tooling and must be removed.",
            )
        )

    if _AUTHOR_YEAR.search(latex):
        issues.append(
            issue(
                "major",
                "STEP 2",
                "Author–year citation style detected. IEEE requires numeric \\cite{key}.",
            )
        )

    pool = {c.citekey for c in context.citation_pool}
    unknown = [k for k in draft.citations_used if k not in pool]
    for key in unknown[:3]:
        issues.append(
            issue(
                "critical",
                "STEP 2",
                f"Unknown citekey '{key}'. This reference does not exist in the bibliography pool.",
            )
        )
    if len(unknown) > 2:
        issues.append(
            issue(
                "critical",
                "STEP 2",
                "Multiple unknown citekeys detected. Bibliography is likely fabricated or mismatched.",
            )
        )

    if draft.section_id in ("introduction", "background", "discussion"):
        if not draft.citations_used:
            issues.append(
                issue(
                    "major",
                    "STEP 2",
                    f"No citations in {draft.section_id}. IEEE papers require supporting literature in this section.",
                )
            )
        elif len(draft.citations_used) < 3:
            issues.append(
                issue(
                    "minor",
                    "STEP 2",
                    f"Fewer than 3 citations in {draft.section_id}. Insufficient literature support.",
                )
            )

    if draft.section_id == "results" and not draft.figures_referenced and plan.figures:
        issues.append(
            issue(
                "major",
                "STEP 3",
                "Results section references no figures. "
                "A comparative study must include at least one data figure.",
            )
        )
    if (
        draft.section_id == "discussion"
        and not draft.figures_referenced
        and not plan.figures
    ):
        issues.append(
            issue(
                "major",
                "STEP 3",
                "Discussion section references no figures and Results has none either. "
                "A comparative study must include at least one data figure.",
            )
        )

    for cite_match in re.finditer(r"\\cite\{([^}]+)\}", latex):
        for raw_key in cite_match.group(1).split(","):
            key = raw_key.strip()
            if key and key not in pool:
                issues.append(
                    issue(
                        "critical",
                        "STEP 2",
                        f"Unknown citekey '{key}' in \\cite{{}}. "
                        "This reference does not exist in the bibliography pool.",
                    )
                )

    if draft.section_id == "results" and not _results_has_measurements(latex):
            issues.append(
                issue(
                    "critical",
                    "STEP 6",
                    "Results section contains no quantitative data. A results section must report "
                    "measured values, not hypotheses or literature references.",
                )
            )

    return issues


def result_from_issues(
    section_id: str,
    issues: list[StructuredIssue],
    *,
    notes: str = "",
    rewrite_attempts: int = 0,
) -> EditorValidationResult:
    return EditorValidationResult(
        section_id=section_id,
        verdict=verdict_from_issues(issues),
        score=score_from_issues(issues),
        issues=flatten_issues(issues),
        notes=notes,
        rewrite_attempts=rewrite_attempts,
    )
