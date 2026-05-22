"""Orchestrator agent (GPT-4o): plan via OpenAI Responses API + function calling + versioned prompt."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pydantic import ValidationError

from ..clients.gemini_client import GeminiClient
from ..clients.openai_client import OpenAIClient
from ..config import ACTIVE_SEARCH_AGENT_IDS, Settings
from ..prompts.loader import (
    load_orchestrator_followup_instruction,
    load_orchestrator_instruction,
)
from ..schemas import (
    GatheredResearchBundle,
    OrchestratorPlan,
    ValidatedResearchBundle,
)
from .orchestrator_tools import ORCHESTRATOR_TOOL_SCHEMAS, OrchestratorPlanBuilder

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FollowupDecision:
    """Result of the post-validation refinement step."""

    gemini_tasks: list[str]
    openai_tasks: list[str]
    reasoning: str

    @property
    def has_tasks(self) -> bool:
        return bool(self.gemini_tasks or self.openai_tasks)


class OrchestratorAgent:
    def __init__(
        self,
        openai_client: OpenAIClient,
        gemini_client: GeminiClient,
        *,
        settings: Settings,
    ) -> None:
        self._openai = openai_client
        self._gemini = gemini_client
        self._settings = settings

    async def create_plan(self, research_goal: str) -> OrchestratorPlan:
        user_prompt = (
            "Research goal from the user:\n\n"
            f"{research_goal.strip()}\n\n"
            "Use the tools in the required order to delegate work, then finalize."
        )
        builder = OrchestratorPlanBuilder(self._settings)
        await self._openai.run_tool_session(
            system=load_orchestrator_instruction(),
            user=user_prompt,
            tools=ORCHESTRATOR_TOOL_SCHEMAS,
            tool_handlers=builder.tool_handlers(),
        )

        if not builder.is_complete():
            hint = (
                "Orchestrator did not call finalize_orchestrator_plan after delegating. "
                "The model may have stopped early; retry or use RESEARCH_ORCHESTRATOR_MODEL=gpt-4o."
            )
            if builder.main_topic and not builder.gemini_tasks:
                hint += " (research goal was set but gemini_search was not delegated.)"
            if builder.gemini_tasks and not builder.validator_tasks:
                hint += " (search was delegated but research_validator was not.)"
            raise ValueError(hint)

        try:
            plan = builder.to_plan()
            OrchestratorPlan.model_validate(plan.model_dump())
        except (ValidationError, ValueError) as exc:
            logger.error("Orchestrator plan failed validation: %s", exc)
            raise ValueError(f"Orchestrator produced invalid plan: {exc}") from exc

        search_count = sum(
            1
            for a in plan.execution_strategy.target_agents
            if a.agent_id in ACTIVE_SEARCH_AGENT_IDS or a.agent_id == "gemini_explorer"
        )
        logger.info(
            "Orchestrator plan: topic=%r, active_search_agents=%d (via tools)",
            plan.research_goal.main_topic,
            search_count,
        )
        return plan

    async def refine_plan(
        self,
        *,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
        validated: ValidatedResearchBundle,
        max_followup_tasks: int = 4,
    ) -> FollowupDecision:
        """Ask the orchestrator to inspect validation results and request follow-ups.

        Returns a :class:`FollowupDecision` whose ``has_tasks`` flag tells the
        pipeline whether another search+validate round should run.
        """
        existing_gemini = [
            t for a in plan.execution_strategy.target_agents
            if a.agent_id == "gemini_search" for t in a.tasks
        ]
        existing_openai = [
            t for a in plan.execution_strategy.target_agents
            if a.agent_id == "openai_search" for t in a.tasks
        ]
        validation_report = [
            {
                "slug": v.slug,
                "agent_id": v.agent_id,
                "task": v.task,
                "verdict": v.verdict,
                "source_quality": v.source_quality,
                "clarity": v.clarity,
                "coverage": v.coverage,
                "gaps": v.gaps,
                "issues": v.issues,
                "source_notes": v.source_notes,
            }
            for v in validated.results
        ]
        gathered_summaries = [
            {
                "task": r.task,
                "agent_id": r.agent_id,
                "success": r.success,
                "source_count": len(r.sources),
                "summary_preview": (r.summary or "")[:600],
            }
            for r in bundle.results
        ]
        payload = {
            "phase": "followup_refinement",
            "research_goal": plan.research_goal.model_dump(),
            "existing_gemini_search_tasks": existing_gemini,
            "existing_openai_search_tasks": existing_openai,
            "gathered_results_summary": gathered_summaries,
            "validation_report": validation_report,
            "followup_budget_total": max_followup_tasks,
        }

        data = await self._gemini.generate_json(
            system=load_orchestrator_followup_instruction(),
            user=json.dumps(payload, indent=2, default=str),
            trace_label="orchestrator_followup",
        )
        reasoning = str(data.get("reasoning") or "").strip()
        gemini_tasks = [str(t).strip() for t in data.get("gemini_followup_tasks") or [] if str(t).strip()]
        openai_tasks = [str(t).strip() for t in data.get("openai_followup_tasks") or [] if str(t).strip()]

        while len(gemini_tasks) + len(openai_tasks) > max_followup_tasks:
            if len(openai_tasks) >= len(gemini_tasks) and openai_tasks:
                openai_tasks.pop()
            elif gemini_tasks:
                gemini_tasks.pop()
            else:
                openai_tasks.pop()

        seen = {t.lower() for t in existing_gemini} | {t.lower() for t in existing_openai}
        gemini_new = [t for t in gemini_tasks if t.lower() not in seen]
        openai_new = [t for t in openai_tasks if t.lower() not in seen]
        if len(gemini_new) != len(gemini_tasks) or len(openai_new) != len(openai_tasks):
            logger.info(
                "Follow-up: dropped %d duplicate task(s) already in initial plan.",
                (len(gemini_tasks) - len(gemini_new)) + (len(openai_tasks) - len(openai_new)),
            )

        if not reasoning:
            reasoning = (
                "No follow-up tasks."
                if not (gemini_new or openai_new)
                else "Follow-up tasks requested from validation gaps."
            )

        return FollowupDecision(
            gemini_tasks=gemini_new,
            openai_tasks=openai_new,
            reasoning=reasoning,
        )
