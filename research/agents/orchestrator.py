"""Orchestrator agent (GPT-4o): plan via OpenAI Responses API + function calling + versioned prompt."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from ..clients.openai_client import OpenAIClient
from ..config import ACTIVE_SEARCH_AGENT_IDS, Settings
from ..prompts.loader import load_orchestrator_instruction
from ..schemas import OrchestratorPlan
from .orchestrator_tools import ORCHESTRATOR_TOOL_SCHEMAS, OrchestratorPlanBuilder

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    def __init__(self, client: OpenAIClient, *, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def create_plan(self, research_goal: str) -> OrchestratorPlan:
        user_prompt = (
            "Research goal from the user:\n\n"
            f"{research_goal.strip()}\n\n"
            "Use the tools in the required order to delegate work, then finalize."
        )
        builder = OrchestratorPlanBuilder(self._settings)
        await self._client.run_tool_session(
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
