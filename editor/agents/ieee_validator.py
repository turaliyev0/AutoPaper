"""IEEE validator agent — checks structure, format, and citation consistency."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from research.clients.gemini_client import GeminiClient

from ..context import EditorContext
from ..prompts.loader import load_ieee_validator_instruction
from ..schemas import EditorPlan, EditorValidationResult, SectionDraft

logger = logging.getLogger(__name__)

AGENT_ID = "ieee_validator"

# ---------------------------------------------------------------------------
# Deterministic pre-checks (pure Python, no LLM)
# ---------------------------------------------------------------------------

_REQUIRED_IEEE_SECTIONS = {"abstract", "introduction", "conclusion", "references"}
_NUMERIC_CITE_PATTERN = re.compile(r"\[\d+\]")
_PIPELINE_WORDS = re.compile(
    r"\b(autopaper|execution_\d+|search agent|validation run)\b",
    re.IGNORECASE,
)
_FIG_REF_PATTERN = re.compile(r"\\ref\{fig:", re.IGNORECASE)


def _deterministic_checks(draft: SectionDraft, plan: EditorPlan) -> list[str]:
    """Run fast rule-based checks before sending to LLM."""
    issues: list[str] = []
    latex = draft.latex_body

    if not latex.strip():
        return ["Section body is empty."]

    # Abstract: word count
    if draft.section_id == "abstract":
        wc = draft.word_count
        limit = 250 if plan.ieee_format == "journal" else 150
        if wc > limit:
            issues.append(
                f"Abstract is {wc} words (IEEE {plan.ieee_format} limit ~{limit})."
            )
        if wc < 50:
            issues.append(f"Abstract is too short ({wc} words).")

    # Pipeline leakage (strict list — no false positives on domain words)
    match = _PIPELINE_WORDS.search(latex)
    if match:
        issues.append(
            f"Section contains internal tool term '{match.group()}'. Remove before submission."
        )

    # Author-year citation style
    if re.search(r"\([\w]+\s+et al\.,?\s+\d{4}\)", latex):
        issues.append(
            "Author–year citation style detected. IEEE requires \\cite{key} style."
        )

    # Figure cross-reference consistency (deterministic — not delegated to LLM)
    if draft.figures_referenced:
        if _FIG_REF_PATTERN.search(latex):
            pass  # at least one proper \ref{fig:...} found — OK
        else:
            issues.append(
                "Figures declared in figures_referenced but no \\ref{fig:...} found in body. "
                "Add Fig.~\\ref{fig:id} or remove from figures_referenced."
            )

    return issues


# ---------------------------------------------------------------------------
# LLM-based validation
# ---------------------------------------------------------------------------


def _build_validation_payload(
    draft: SectionDraft,
    plan: EditorPlan,
    context: EditorContext,
) -> str:
    citation_pool_keys = [c.citekey for c in context.citation_pool]
    payload: dict[str, Any] = {
        "section_id": draft.section_id,
        "heading": draft.heading,
        "ieee_format": plan.ieee_format,
        "word_count": draft.word_count,
        "citations_used": draft.citations_used,
        "citation_pool_keys": citation_pool_keys[:40],
        "figures_referenced": draft.figures_referenced,
        "latex_body_preview": draft.latex_body[:1500],
        "validation_focus": plan.validation_focus,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


class IeeeValidatorAgent:
    def __init__(self, client: GeminiClient) -> None:
        self._client = client
        self._system = load_ieee_validator_instruction()

    async def validate_section(
        self,
        draft: SectionDraft,
        plan: EditorPlan,
        context: EditorContext,
    ) -> EditorValidationResult:
        # Deterministic checks first
        det_issues = _deterministic_checks(draft, plan)

        if not draft.success:
            return EditorValidationResult(
                section_id=draft.section_id,
                verdict="fail",
                issues=[draft.error or "Section failed to generate."],
                notes="Section did not complete successfully.",
            )

        user = _build_validation_payload(draft, plan, context)
        try:
            data = await self._client.generate_json(
                system=self._system,
                user=user,
                trace_label=f"ieee_validator:{draft.section_id}",
            )
        except Exception as exc:
            logger.warning("IEEE validator LLM failed for %s: %s", draft.section_id, exc)
            data = {}

        llm_issues = [str(i) for i in (data.get("issues") or []) if str(i).strip()]
        all_issues = det_issues + llm_issues

        raw_verdict = str(data.get("verdict") or "pass").lower()
        if raw_verdict not in ("pass", "warn", "fail"):
            raw_verdict = "pass"

        # Deterministic fails override LLM pass
        if det_issues and raw_verdict == "pass":
            raw_verdict = "warn"

        return EditorValidationResult(
            section_id=draft.section_id,
            verdict=raw_verdict,  # type: ignore[arg-type]
            issues=all_issues,
            notes=str(data.get("notes") or "").strip(),
        )

    async def validate_all(
        self,
        drafts: list[SectionDraft],
        plan: EditorPlan,
        context: EditorContext,
    ) -> list[EditorValidationResult]:
        coros = [
            self.validate_section(draft, plan, context)
            for draft in drafts
        ]
        logger.info("IeeeValidatorAgent: validating %d sections", len(coros))
        results = await asyncio.gather(*coros, return_exceptions=True)

        out: list[EditorValidationResult] = []
        for draft, item in zip(drafts, results):
            if isinstance(item, BaseException):
                logger.exception("Validator crashed for %s: %s", draft.section_id, item)
                out.append(EditorValidationResult(
                    section_id=draft.section_id,
                    verdict="fail",
                    issues=[str(item)],
                    notes="Validator crashed.",
                ))
            else:
                out.append(item)
        return out
