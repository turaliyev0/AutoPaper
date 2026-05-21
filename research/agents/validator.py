"""Research validator — per-task source and clarity checks (Gemini)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from ..clients.gemini_client import validator_client
from ..config import Settings
from ..prompts.loader import load_research_validator_instruction
from ..research_storage import load_research_manifest, load_task_result
from ..schemas import (
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


def _deterministic_verdict(result: GatheredTaskResult) -> dict[str, str | list[str]]:
    """Rule-based floor before / without LLM."""
    if not result.success:
        return {
            "verdict": "fail",
            "source_quality": "missing",
            "clarity": "unclear",
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
                "issues": ["Mismatch review summary is empty."],
                "source_notes": "Figure-text mismatch task — no sources required, but summary is missing.",
            }
        return {
            "verdict": "pass",
            "source_quality": "missing",
            "clarity": "clear",
            "issues": [],
            "source_notes": "Figure-text mismatch task — no literature sources required per task instructions.",
        }

    if not result.sources:
        return {
            "verdict": "fail",
            "source_quality": "missing",
            "clarity": "unclear",
            "issues": ["No sources listed in search output."],
            "source_notes": "Summary is not backed by bibliographic sources.",
        }
    if not _has_citable_sources(result.sources):
        return {
            "verdict": "warn",
            "source_quality": "weak",
            "clarity": "unclear",
            "issues": ["Sources lack verifiable bibliographic detail (year, DOI, or author–year)."],
            "source_notes": "Treat findings as illustrative until sources are improved.",
        }
    if not result.summary.strip():
        return {
            "verdict": "warn",
            "source_quality": "clear",
            "clarity": "unclear",
            "issues": ["Summary is empty."],
            "source_notes": "Sources present but summary missing.",
        }
    return {
        "verdict": "pass",
        "source_quality": "clear",
        "clarity": "clear",
        "issues": [],
        "source_notes": "Sources appear bibliographic; summary present.",
    }


class ResearchValidator:
    def __init__(self, settings: Settings) -> None:
        self._client = validator_client(settings)
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

        issues_raw = data.get("issues") or baseline["issues"]
        issues = [str(i).strip() for i in issues_raw if str(i).strip()] if isinstance(issues_raw, list) else []

        return ValidatedTaskResult(
            slug=slug,
            research_filename=research_filename,
            agent_id=result.agent_id,
            task=result.task,
            verdict=verdict,  # type: ignore[arg-type]
            source_quality=source_quality,  # type: ignore[arg-type]
            clarity=clarity,  # type: ignore[arg-type]
            issues=issues,
            source_notes=str(data.get("source_notes") or baseline["source_notes"]).strip(),
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
