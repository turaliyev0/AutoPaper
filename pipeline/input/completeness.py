"""Detect incomplete or truncated paper input before research (step 05+)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pipeline.editor.manuscript_metrics import has_measured_outcomes

_RESULTS_CLAIM = re.compile(
    r"results?\s+(?:demonstrate|show|indicate|confirm|reveal)|"
    r"we\s+(?:found|observed|measured|demonstrated)|"
    r"significantly\s+(?:increased|decreased|reduced|improved)",
    re.IGNORECASE,
)
_TRUNCATION = re.compile(
    r"(?:\.\.\.|…)\s*$|(?:etc\.?\s*$)|(?:continues?\s*$)|(?:see\s+supplement)",
    re.IGNORECASE,
)
_PLACEHOLDER_METHODS = frozenset(
    {
        "no method notes provided.",
        "no methods provided.",
        "tbd",
        "n/a",
    },
)


@dataclass(frozen=True)
class InputGap:
    id: str
    severity: Literal["required", "recommended"]
    question: str
    hint: str
    reason: str
    target_path: str  # relative to input project root


@dataclass
class CompletenessReport:
    gaps: list[InputGap] = field(default_factory=list)

    @property
    def has_blocking_gaps(self) -> bool:
        return any(g.severity == "required" for g in self.gaps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocking": self.has_blocking_gaps,
            "gaps": [
                {
                    "id": g.id,
                    "severity": g.severity,
                    "question": g.question,
                    "hint": g.hint,
                    "reason": g.reason,
                    "target_path": g.target_path,
                }
                for g in self.gaps
            ],
        }


def _text_blob_from_bundle(bundle: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("description_files", "details_files"):
        for item in bundle.get(key) or []:
            if isinstance(item, dict):
                parts.append(str(item.get("content") or ""))
    return "\n".join(parts)


def _char_counts(bundle: dict[str, Any]) -> tuple[int, int]:
    desc = sum(
        len(str(item.get("content") or ""))
        for item in bundle.get("description_files") or []
        if isinstance(item, dict)
    )
    det = sum(
        len(str(item.get("content") or ""))
        for item in bundle.get("details_files") or []
        if isinstance(item, dict)
    )
    return desc, det


def _has_results_file(bundle: dict[str, Any]) -> bool:
    for item in bundle.get("details_files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("relative_path") or "").lower()
        content = str(item.get("content") or "").strip()
        if "result" in path and len(content) > 40:
            return True
    return False


def _methods_is_placeholder(bundle: dict[str, Any]) -> bool:
    for item in bundle.get("details_files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("relative_path") or "").lower()
        if "method" not in path and "details" not in path:
            continue
        content = str(item.get("content") or "").strip().lower()
        if not content or content in _PLACEHOLDER_METHODS:
            return True
        if len(content) < 80:
            return True
    return False


def _looks_truncated(bundle: dict[str, Any]) -> bool:
    for key in ("description_files", "details_files"):
        for item in bundle.get(key) or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if len(content) < 120:
                continue
            last_line = content.splitlines()[-1].strip()
            if _TRUNCATION.search(last_line):
                return True
    return False


def analyze_completeness(
    final: dict[str, Any],
    bundle: dict[str, Any],
) -> CompletenessReport:
    """Return gaps that should be filled before research starts."""
    gaps: list[InputGap] = []
    desc_chars, details_chars = _char_counts(bundle)
    blob = _text_blob_from_bundle(bundle)
    measured = has_measured_outcomes(final)
    has_results_file = _has_results_file(bundle)
    claims_results = bool(_RESULTS_CLAIM.search(str(final.get("summary") or "")))
    claims_results = claims_results or bool(_RESULTS_CLAIM.search(blob))

    if desc_chars < 200:
        gaps.append(
            InputGap(
                id="short_overview",
                severity="required",
                question=(
                    "The research overview is very short. Please provide the background, "
                    "objective, and what this study investigates (2–4 paragraphs)."
                ),
                hint="Include motivation, hypothesis, and what was compared or measured.",
                reason=f"Description text is only ~{desc_chars} characters.",
                target_path="description/overview_supplement.md",
            )
        )

    if details_chars < 150 or _methods_is_placeholder(bundle):
        gaps.append(
            InputGap(
                id="missing_methods",
                severity="required",
                question=(
                    "Methods / experimental design are missing or too brief. "
                    "Describe subjects, materials, groups, procedures, metrics, and statistics."
                ),
                hint="Sample size, duration, instruments, endpoints, and analysis tests.",
                reason="Method notes are empty, placeholder, or under ~80 characters.",
                target_path="details/method_notes_supplement.txt",
            )
        )

    if not measured and not has_results_file:
        sev: Literal["required", "recommended"] = (
            "required" if claims_results else "recommended"
        )
        gaps.append(
            InputGap(
                id="missing_results",
                severity=sev,
                question=(
                    "No quantitative results were found in the input. "
                    "Provide measured outcomes (values with units, sample sizes, p-values, "
                    "or a results summary paragraph)."
                ),
                hint=(
                    "Example: impedance at week 4 (kΩ), SNR (dB), histology scores, n=12, p<0.05."
                ),
                reason=(
                    "No results file and no measured-outcome lines in standardized manuscript."
                    + (" Narrative claims findings exist." if claims_results else "")
                ),
                target_path="details/results_supplement.txt",
            )
        )
    elif claims_results and not measured:
        gaps.append(
            InputGap(
                id="results_not_quantified",
                severity="required",
                question=(
                    "The overview claims results, but no numeric measurements were extracted. "
                    "Add concrete measured values with units."
                ),
                hint="List each metric, group comparison, and time point with numbers.",
                reason="Summary claims results without quantitative evidence in structured output.",
                target_path="details/results_supplement.txt",
            )
        )

    if _looks_truncated(bundle):
        gaps.append(
            InputGap(
                id="truncated_text",
                severity="recommended",
                question=(
                    "Some input text looks cut off or incomplete. "
                    "Paste any missing paragraphs or continuation here."
                ),
                hint="Complete any section that ends abruptly or with '...'.",
                reason="Detected truncation markers or incomplete ending lines.",
                target_path="details/additional_context.txt",
            )
        )

    for block in final.get("text_blocks") or []:
        if not isinstance(block, dict):
            continue
        if block.get("citation_gap") is True:
            rel = str(block.get("relative_path") or "text")
            gaps.append(
                InputGap(
                    id=f"citation_gap_{rel.replace('/', '_')}",
                    severity="recommended",
                    question=(
                        f"The file {rel} has no bibliographic citations. "
                        "If you have key references for this section, list them (Author, Year, Title)."
                    ),
                    hint="Optional - skip by pressing Enter in CLI or omit in API answers.",
                    reason=f"No citations detected in {rel}.",
                    target_path="details/references_notes.txt",
                )
            )
            break  # one prompt is enough

    # Deduplicate by id
    seen: set[str] = set()
    unique: list[InputGap] = []
    for g in gaps:
        if g.id in seen:
            continue
        seen.add(g.id)
        unique.append(g)
    return CompletenessReport(gaps=unique)
