"""Gemini search agent — model knowledge + structured JSON per subtask."""

from __future__ import annotations

import logging

from ...clients.gemini_client import gemini_search_client
from ...config import Settings
from ...prompts.loader import load_gemini_search_instruction
from ...manuscript_context import ManuscriptContext
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import failed_result, result_from_json, task_user_payload

logger = logging.getLogger(__name__)

AGENT_ID = "gemini_search"


class GeminiSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._client = gemini_search_client(settings)
        self._system = load_gemini_search_instruction()

    async def run_task(
        self,
        task: str,
        plan: OrchestratorPlan,
        *,
        manuscript: ManuscriptContext | None = None,
    ) -> GatheredTaskResult:
        try:
            data = await self._client.generate_json(
                system=self._system,
                user=task_user_payload(task, plan, manuscript=manuscript),
                trace_label=f"gemini_search:{task[:48]}",
            )
            return result_from_json(task=task, agent_id=AGENT_ID, data=data)
        except Exception as exc:
            logger.exception("Gemini search failed: %s", task)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
