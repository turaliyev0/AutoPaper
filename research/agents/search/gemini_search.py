"""Gemini search agent — model knowledge + structured JSON per subtask."""

from __future__ import annotations

import logging

from ...clients.gemini_client import GeminiClient
from ...config import Settings
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import RESEARCH_TASK_JSON_SYSTEM, failed_result, result_from_json, task_user_payload

logger = logging.getLogger(__name__)

AGENT_ID = "gemini_search"

GEMINI_SEARCH_SYSTEM = (
    RESEARCH_TASK_JSON_SYSTEM
    + "\nYou use Gemini model knowledge only (no live web). Do not invent URLs."
)


class GeminiSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._client = GeminiClient(settings)

    async def run_task(self, task: str, plan: OrchestratorPlan) -> GatheredTaskResult:
        try:
            data = await self._client.generate_json(
                system=GEMINI_SEARCH_SYSTEM,
                user=task_user_payload(task, plan),
            )
            return result_from_json(task=task, agent_id=AGENT_ID, data=data)
        except Exception as exc:
            logger.exception("Gemini search failed: %s", task)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
