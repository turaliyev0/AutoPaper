"""Research validator — per-task source and clarity checks (Gemini)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from ..clients.evaluator_client import research_validator_client
from ..config import Settings
from ..task_kinds import TaskKind, classify_task, provenance_for_kind
from ..prompts.loader import load_research_validator_instruction
from ..research_storage import load_research_manifest, load_task_result, task_artifact_slug
from ..schemas import (
    GatheredResearchBundle,
    GatheredTaskResult,
    OrchestratorPlan,
    ValidatedResearchBundle,
    ValidatedTaskResult,
)
from .search.base import _has_citable_sources

logger = logging.getLogger(__name__)

AGENT_ID = "research_validator"


_MISMATCH_PHRASE = "grounding in literature is optional"


def _is_mismatch_review(task: str) -> bool:
    """Return True when the task is a figure-text mismatch review that does not require sources."""
    return _MISMATCH_PHRASE in task.lower()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _overview_from_summary(result: GatheredTaskResult, *, max_sentences: int = 8) -> str:
    """Build overview sentences from the search summary when the validator omits overview."""
    text = (result.summary or "").strip()
    if not text:
        return "This research task did not produce a usable summary."
    sentences = _split_sentences(text)
    if not sentences:
        return text[:900]
    return " ".join(sentences[:max_sentences])


def _coerce_overview(raw: str, result: GatheredTaskResult) -> str:
    """Normalize to 5–10 sentences."""
    overview = str(raw or "").strip()
    if not overview:
        overview = _overview_from_summary(result)

    sentences = _split_sentences(overview)
    if len(sentences) < 5:
        extra = _split_sentences(_overview_from_summary(result))
        merged: list[str] = []
        seen: set[str] = set()
        for s in sentences + extra:
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(s)
            if len(merged) >= 10:
                break
        sentences = merged if len(merged) >= 5 else extra[:10]

    if len(sentences) > 10:
        sentences = sentences[:10]
    return " ".join(sentences)


def _deterministic_verdict(result: GatheredTaskResult) -> dict[str, str | list[str]]:
    """Rule-based floor before / without LLM."""
    if not result.success:
        return {
            "verdict": "fail",
            "source_quality": "missing",
            "clarity": "unclear",
            "coverage": "insufficient",
            "gaps": ["Search task failed; no information gathered."],
            "issues": [result.error or "Search task failed."],
            "source_notes": "Task did not complete successfully.",
        }

    # Figure-text mismatch reviews explicitly opt out of source requirements.
    if _is_mismatch_review(result.task):
        if not result.summary.strip():
            return {
                "verdict": "warn",
                "source_quality": "missing",
                "clarity": "unclear",
                "coverage": "insufficient",
                "gaps": ["Mismatch summary missing — fix recommendation not produced."],
                "issues": ["Mismatch review summary is empty."],
                "source_notes": "Figure-text mismatch task — no sources required, but summary is missing.",
            }
        return {
            "verdict": "pass",
            "source_quality": "missing",
            "clarity": "clear",
            "coverage": "sufficient",
            "gaps": [],
            "issues": [],
            "source_notes": "Figure-text mismatch task — no literature sources required per task instructions.",
        }

    if not result.sources:
        return {
            "verdict": "fail",
            "source_quality": "missing",
            "clarity": "unclear",
            "coverage": "insufficient",
            "gaps": ["No literature sources gathered for this subtask."],
            "issues": ["No sources listed in search output."],
            "source_notes": "Summary is not backed by bibliographic sources.",
        }
    if not _has_citable_sources(result.sources):
        return {
            "verdict": "warn",
            "source_quality": "weak",
            "clarity": "unclear",
            "coverage": "partial",
            "gaps": ["Sources lack verifiable bibliographic detail; corroborating studies needed."],
            "issues": ["Sources lack verifiable bibliographic detail (year, DOI, or author–year)."],
            "source_notes": "Treat findings as illustrative until sources are improved.",
        }
    if not result.summary.strip():
        return {
            "verdict": "warn",
            "source_quality": "clear",
            "clarity": "unclear",
            "coverage": "partial",
            "gaps": ["Summary is empty; sources cannot be interpreted."],
            "issues": ["Summary is empty."],
            "source_notes": "Sources present but summary missing.",
        }
    # Heuristic: a single source is rarely enough coverage for a research subtopic.
    if len(result.sources) < 2:
        return {
            "verdict": "warn",
            "source_quality": "clear",
            "clarity": "clear",
            "coverage": "partial",
            "gaps": ["Only one source — needs corroborating studies."],
            "issues": [],
            "source_notes": "Sources present but only one cited; corroborating studies recommended.",
        }
    return {
        "verdict": "pass",
        "source_quality": "clear",
        "clarity": "clear",
        "coverage": "partial",
        "gaps": [],
        "issues": [],
        "source_notes": "Sources appear bibliographic; summary present.",
    }


class ResearchValidator:
    def __init__(self, settings: Settings) -> None:
        self._client = research_validator_client(settings)
        self._system = load_research_validator_instruction()

    async def validate_task(
        self,
        *,
        slug: str,
        research_filename: str,
        result: GatheredTaskResult,
        plan: OrchestratorPlan,
    ) -> ValidatedTaskResult:
        baseline = _deterministic_verdict(result)
        payload = {
            "research_goal": plan.research_goal.model_dump(),
            "validator_focus": (plan.validator_agent().tasks if plan.validator_agent() else []),
            "search_result": result.model_dump(),
            "deterministic_baseline": baseline,
        }
        try:
            data = await self._client.generate_json(
                system=self._system,
                user=json.dumps(payload, indent=2, default=str),
                trace_label=f"research_validator:{slug}",
            )
        except Exception as exc:
            logger.warning("Validator LLM failed for %s: %s", slug, exc)
            data = dict(baseline)

        verdict = str(data.get("verdict") or baseline["verdict"]).lower()
        if verdict not in ("pass", "warn", "fail"):
            verdict = str(baseline["verdict"])

        # Never upgrade a deterministic fail to pass, UNLESS this is a mismatch review
        # (where the deterministic baseline already handles the pass correctly).
        if baseline["verdict"] == "fail" and verdict == "pass" and not _is_mismatch_review(result.task):
            verdict = "fail"

        source_quality = str(data.get("source_quality") or baseline["source_quality"]).lower()
        if source_quality not in ("clear", "weak", "missing"):
            source_quality = str(baseline["source_quality"])

        clarity = str(data.get("clarity") or baseline["clarity"]).lower()
        if clarity not in ("clear", "unclear", "contradictory"):
            clarity = str(baseline["clarity"])

        coverage = str(data.get("coverage") or baseline["coverage"]).lower()
        if coverage not in ("sufficient", "partial", "insufficient"):
            coverage = str(baseline["coverage"])

        # If the deterministic baseline says insufficient (e.g. search failed, no sources),
        # never let the LLM upgrade coverage to sufficient.
        if baseline["coverage"] == "insufficient" and coverage == "sufficient":
            coverage = "insufficient"

        gaps_raw = data.get("gaps") or baseline["gaps"]
        gaps = [str(g).strip() for g in gaps_raw if str(g).strip()] if isinstance(gaps_raw, list) else []
        # Hard cap to keep payload reasonable for the follow-up orchestrator.
        gaps = gaps[:4]

        # Force consistency: insufficient coverage with no gaps listed is useless to the
        # follow-up orchestrator, so synthesize a generic gap from the issues / baseline.
        if coverage == "insufficient" and not gaps:
            baseline_gaps = baseline["gaps"] if isinstance(baseline["gaps"], list) else []
            gaps = [str(g) for g in baseline_gaps] or [
                "Coverage marked insufficient but no specific gap listed."
            ]

        issues_raw = data.get("issues") or baseline["issues"]
        issues = [str(i).strip() for i in issues_raw if str(i).strip()] if isinstance(issues_raw, list) else []

        overview = _coerce_overview(str(data.get("overview") or ""), result)

        task_kind: TaskKind = classify_task(result.task)
        data_provenance = str(data.get("data_provenance") or "").lower()
        if data_provenance not in ("literature_only", "manuscript_only", "mixed", "unknown"):
            data_provenance = provenance_for_kind(task_kind)
        # Never allow LLM to mark benchmark tasks as own-study data.
        if task_kind == "literature_benchmark" and data_provenance != "literature_only":
            data_provenance = "literature_only"
            issues.append(
                "Quantitative benchmark task must be literature_only "
                "(values are from prior studies, not this experiment)."
            )
            if verdict == "pass" and coverage == "sufficient":
                verdict = "warn"

        return ValidatedTaskResult(
            slug=slug,
            research_filename=research_filename,
            agent_id=result.agent_id,
            task=result.task,
            verdict=verdict,  # type: ignore[arg-type]
            source_quality=source_quality,  # type: ignore[arg-type]
            clarity=clarity,  # type: ignore[arg-type]
            coverage=coverage,  # type: ignore[arg-type]
            gaps=gaps,
            issues=issues,
            source_notes=str(data.get("source_notes") or baseline["source_notes"]).strip(),
            task_kind=task_kind,
            data_provenance=data_provenance,  # type: ignore[arg-type]
            overview=overview,
        )

    async def validate_all(
        self,
        plan: OrchestratorPlan,
        research_dir: Path,
    ) -> ValidatedResearchBundle:
        manifest = load_research_manifest(research_dir)
        tasks = manifest.get("tasks") or []

        async def _one(entry: dict) -> ValidatedTaskResult:
            filename = str(entry["filename"])
            slug = str(entry["slug"])
            result = load_task_result(research_dir, filename)
            return await self.validate_task(
                slug=slug,
                research_filename=filename,
                result=result,
                plan=plan,
            )

        if not tasks:
            return ValidatedResearchBundle(plan=plan, results=[])

        logger.info("ResearchValidator: validating %d task files", len(tasks))
        results = await asyncio.gather(*[_one(t) for t in tasks])
        return ValidatedResearchBundle(plan=plan, results=list(results))

    async def validate_bundle(
        self,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
        *,
        start_index: int = 1,
    ) -> ValidatedResearchBundle:
        """Validate an in-memory bundle (no disk reads).

        Assigns the same slugs as :func:`research_storage.write_research_bundle`
        so the validation artifacts stay aligned with the eventual research files.
        """
        if not bundle.results:
            return ValidatedResearchBundle(plan=plan, results=[])

        async def _one(idx: int, result: GatheredTaskResult) -> ValidatedTaskResult:
            slug = task_artifact_slug(result.agent_id, idx, result.task)
            filename = f"{slug}.json"
            return await self.validate_task(
                slug=slug,
                research_filename=filename,
                result=result,
                plan=plan,
            )

        logger.info("ResearchValidator: validating %d in-memory results", len(bundle.results))
        results = await asyncio.gather(
            *[
                _one(idx, r)
                for idx, r in enumerate(bundle.results, start=start_index)
            ],
        )
        return ValidatedResearchBundle(plan=plan, results=list(results))
