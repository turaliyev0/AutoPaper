"""IEEE validator agent — strict pre-submission gate (v003) with score-based rewrites."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pipeline.research.clients.gemini_client import GeminiClient

from ..context import EditorContext
from ..prompts.loader import load_ieee_validator_instruction
from ..schemas import EditorPlan, EditorValidationResult, SectionDraft, SectionSpec

logger = logging.getLogger(__name__)

AGENT_ID = "ieee_validator"

StructuredIssue = dict[str, str]

_PIPELINE_WORDS = re.compile(
    r"\b(autopaper|execution_\d+|search agent|validation run)\b",
    re.IGNORECASE,
)
_AUTHOR_YEAR = re.compile(r"\([\w]+\s+et al\.,?\s+\d{4}\)")


def _issue(
    severity: Literal["critical", "major", "minor"],
    step: str,
    message: str,
) -> StructuredIssue:
    return {"severity": severity, "step": step, "message": message}


def _flatten_issues(raw: list[Any]) -> list[str]:
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


def _score_from_issues(issues: list[StructuredIssue]) -> int:
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


def _verdict_from_issues(issues: list[StructuredIssue]) -> Literal["pass", "warn", "fail"]:
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


def _parse_llm_issues(raw: Any) -> list[StructuredIssue]:
    if not isinstance(raw, list):
        return []
    out: list[StructuredIssue] = []
    for item in raw:
        if isinstance(item, dict):
            msg = str(item.get("message") or "").strip()
            if not msg:
                continue
            sev = str(item.get("severity") or "minor").lower()
            if sev not in ("critical", "major", "minor"):
                sev = "minor"
            step = str(item.get("step") or "LLM").strip() or "LLM"
            out.append(_issue(sev, step, msg))  # type: ignore[arg-type]
        elif str(item).strip():
            out.append(_issue("minor", "LLM", str(item).strip()))
    return out


def _infer_device_type(context: EditorContext) -> str:
    parts = [
        context.title,
        context.manuscript.summary,
        " ".join(context.manuscript.experimental_design_bullets()),
    ]
    blob = " ".join(parts).lower()
    if "flexible" in blob:
        return "flexible_neural_probe"
    return ""


def _deterministic_checks(
    draft: SectionDraft,
    plan: EditorPlan,
    context: EditorContext,
) -> list[StructuredIssue]:
    """Fast rule-based checks aligned with validator v003 STEPs."""
    issues: list[StructuredIssue] = []
    latex = draft.latex_body
    non_ws = len(re.sub(r"\s", "", latex))

    if not latex.strip() or non_ws < 20:
        return [
            _issue(
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
                _issue("critical", "STEP 1", "Abstract is too short to meet IEEE minimum.")
            )
        elif wc > limit:
            issues.append(
                _issue(
                    "major",
                    "STEP 1",
                    f"Abstract exceeds IEEE {plan.ieee_format} {limit}-word limit.",
                )
            )

    match = _PIPELINE_WORDS.search(latex)
    if match:
        term = match.group()
        issues.append(
            _issue(
                "critical",
                "STEP 4",
                f"Internal pipeline term '{term}' found in manuscript body. "
                "This reveals AI generation tooling and must be removed.",
            )
        )

    if _AUTHOR_YEAR.search(latex):
        issues.append(
            _issue(
                "major",
                "STEP 2",
                "Author–year citation style detected. IEEE requires numeric \\cite{key}.",
            )
        )

    pool = {c.citekey for c in context.citation_pool}
    unknown = [k for k in draft.citations_used if k not in pool]
    for key in unknown[:3]:
        issues.append(
            _issue(
                "critical",
                "STEP 2",
                f"Unknown citekey '{key}'. This reference does not exist in the bibliography pool.",
            )
        )
    if len(unknown) > 2:
        issues.append(
            _issue(
                "critical",
                "STEP 2",
                "Multiple unknown citekeys detected. Bibliography is likely fabricated or mismatched.",
            )
        )

    if draft.section_id in ("introduction", "background", "discussion"):
        if not draft.citations_used:
            issues.append(
                _issue(
                    "major",
                    "STEP 2",
                    f"No citations in {draft.section_id}. IEEE papers require supporting literature in this section.",
                )
            )
        elif len(draft.citations_used) < 3:
            issues.append(
                _issue(
                    "minor",
                    "STEP 2",
                    f"Fewer than 3 citations in {draft.section_id}. Insufficient literature support.",
                )
            )

    if draft.section_id in ("results", "discussion") and not draft.figures_referenced:
        issues.append(
            _issue(
                "major",
                "STEP 3",
                "Results/Discussion section references no figures. "
                "A comparative study must include at least one data figure.",
            )
        )

    if draft.section_id == "results" and not re.search(r"\d", latex):
        issues.append(
            _issue(
                "critical",
                "STEP 6",
                "Results section contains no quantitative data. A results section must report "
                "measured values, not hypotheses or literature references.",
            )
        )

    return issues


def _build_validation_payload(
    draft: SectionDraft,
    plan: EditorPlan,
    context: EditorContext,
) -> str:
    citation_pool_keys = [c.citekey for c in context.citation_pool]
    mismatch_flags = [
        {"image": f.get("image_path"), "issue": f.get("issue")}
        for f in context.manuscript.mismatch_flags
    ]
    payload: dict[str, Any] = {
        "section_id": draft.section_id,
        "heading": draft.heading,
        "ieee_format": plan.ieee_format,
        "word_count": draft.word_count,
        "citations_used": draft.citations_used,
        "citation_pool_keys": citation_pool_keys[:60],
        "figures_referenced": draft.figures_referenced,
        "latex_body_preview": draft.latex_body[:4000],
        "validation_focus": plan.validation_focus,
        "mismatch_flags": mismatch_flags,
        "device_type": _infer_device_type(context),
        "experimental_design": context.manuscript.experimental_design_bullets()[:12],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _result_from_issues(
    section_id: str,
    issues: list[StructuredIssue],
    *,
    notes: str = "",
    rewrite_attempts: int = 0,
) -> EditorValidationResult:
    verdict = _verdict_from_issues(issues)
    score = _score_from_issues(issues)
    flat = _flatten_issues(issues)
    return EditorValidationResult(
        section_id=section_id,
        verdict=verdict,
        score=score,
        issues=flat,
        notes=notes,
        rewrite_attempts=rewrite_attempts,
    )


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
        det_issues = _deterministic_checks(draft, plan, context)
        if any(i.get("severity") == "critical" for i in det_issues) and (
            not draft.latex_body.strip()
            or len(re.sub(r"\s", "", draft.latex_body)) < 20
        ):
            return _result_from_issues(
                draft.section_id,
                det_issues,
                notes="Section body missing or stub; LLM validation skipped.",
            )

        if not draft.success:
            return EditorValidationResult(
                section_id=draft.section_id,
                verdict="fail",
                score=0,
                issues=[draft.error or "Section failed to generate."],
                notes="Section did not complete successfully.",
            )

        user = _build_validation_payload(draft, plan, context)
        llm_issues: list[StructuredIssue] = []
        notes = ""
        try:
            data = await self._client.generate_json(
                system=self._system,
                user=user,
                trace_label=f"ieee_validator:{draft.section_id}",
            )
            llm_issues = _parse_llm_issues(data.get("issues"))
            notes = str(data.get("notes") or "").strip()
            llm_score = data.get("score")
            llm_verdict = str(data.get("verdict") or "").lower()
        except Exception as exc:
            logger.warning("IEEE validator LLM failed for %s: %s", draft.section_id, exc)
            llm_score = None
            llm_verdict = ""
            notes = f"LLM validation failed: {exc}"

        merged = det_issues + llm_issues
        result = _result_from_issues(draft.section_id, merged, notes=notes)

        if isinstance(llm_score, (int, float)) and llm_issues and not det_issues:
            result.score = max(0, min(100, int(llm_score)))
            if llm_verdict in ("pass", "warn", "fail"):
                computed = _verdict_from_issues(llm_issues)
                llm_v: Literal["pass", "warn", "fail"] = llm_verdict  # type: ignore[assignment]
                if computed == "fail" or (computed == "warn" and llm_v == "pass"):
                    result.verdict = computed
                else:
                    result.verdict = llm_v
                if result.verdict == "pass" and result.issues:
                    result.verdict = "warn"

        if det_issues:
            recomputed = _result_from_issues(draft.section_id, merged, notes=notes)
            result.verdict = recomputed.verdict
            result.score = recomputed.score
            result.issues = recomputed.issues

        return result

    async def validate_all(
        self,
        drafts: list[SectionDraft],
        plan: EditorPlan,
        context: EditorContext,
        *,
        run_dir: Path | None = None,
        persist_each: bool = False,
    ) -> list[EditorValidationResult]:
        results, _ = await self.validate_all_with_rewrites(
            drafts,
            plan,
            context,
            writer=None,
            threshold=101,
            max_rewrites=0,
            run_dir=run_dir,
            persist_each=persist_each,
        )
        return results

    async def validate_all_with_rewrites(
        self,
        drafts: list[SectionDraft],
        plan: EditorPlan,
        context: EditorContext,
        writer: Any | None,
        *,
        threshold: int,
        max_rewrites: int,
        run_dir: Path | None = None,
        persist_each: bool = False,
    ) -> tuple[list[EditorValidationResult], list[SectionDraft]]:
        from ..agents.section_writer import SectionWriterAgent
        from ..storage import append_editor_validation_result

        spec_by_id = {s.section_id: s for s in plan.sections}
        draft_by_id = {d.section_id: d for d in drafts}

        logger.info(
            "IeeeValidatorAgent: validating %d sections (threshold=%d, max_rewrites=%d)",
            len(drafts),
            threshold,
            max_rewrites,
        )
        out: list[EditorValidationResult] = []
        for idx, draft in enumerate(drafts):
            if idx > 0:
                await asyncio.sleep(1.0)
            current = draft_by_id.get(draft.section_id, draft)
            try:
                result = await self.validate_section(current, plan, context)
                attempts = 0
                spec = spec_by_id.get(current.section_id)

                while (
                    attempts < max_rewrites
                    and writer is not None
                    and isinstance(writer, SectionWriterAgent)
                    and spec is not None
                    and result.needs_rewrite(threshold=threshold)
                ):
                    attempts += 1
                    logger.info(
                        "Rewriting section %s (score=%d, verdict=%s, attempt %d/%d)",
                        current.section_id,
                        result.score,
                        result.verdict,
                        attempts,
                        max_rewrites,
                    )
                    current = await writer.rewrite_section(
                        spec,
                        context,
                        prior=current,
                        validation=result,
                    )
                    draft_by_id[current.section_id] = current
                    await asyncio.sleep(1.0)
                    result = await self.validate_section(current, plan, context)
                    result.rewrite_attempts = attempts

                out.append(result)
            except asyncio.CancelledError:
                logger.warning("IEEE validation cancelled for %s", current.section_id)
                result = EditorValidationResult(
                    section_id=current.section_id,
                    verdict="fail",
                    score=0,
                    issues=[
                        "Validation interrupted (API reload or stop). Re-run with --editor-resume.",
                    ],
                    notes="CancelledError during Gemini call.",
                )
                out.append(result)
                if persist_each and run_dir is not None:
                    append_editor_validation_result(run_dir, result)
                raise
            except Exception as exc:
                logger.exception("Validator crashed for %s: %s", current.section_id, exc)
                result = EditorValidationResult(
                    section_id=current.section_id,
                    verdict="fail",
                    score=0,
                    issues=[str(exc)],
                    notes="Validator crashed.",
                )
                out.append(result)
            if persist_each and run_dir is not None:
                append_editor_validation_result(run_dir, out[-1])

        updated = [draft_by_id.get(d.section_id, d) for d in drafts]
        return out, updated
