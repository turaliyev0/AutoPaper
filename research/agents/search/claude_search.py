"""Claude search agent — structured research JSON per subtask."""

from __future__ import annotations

import logging

from ...clients.anthropic_client import AnthropicClient
from ...config import Settings
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import RESEARCH_TASK_JSON_SYSTEM, failed_result, result_from_json, task_user_payload

logger = logging.getLogger(__name__)

AGENT_ID = "claude_search"

CLAUDE_SEARCH_SYSTEM = (
    RESEARCH_TASK_JSON_SYSTEM
    + "\nYou use Claude model knowledge only (no live web). Do not invent URLs."
)


class ClaudeSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._client = AnthropicClient(
            settings,
            api_key=settings.claude_search_api_key,
            model=settings.claude_search_model,
        )

    async def run_task(self, task: str, plan: OrchestratorPlan) -> GatheredTaskResult:
        try:
            data = await self._client.generate_json(
                system=CLAUDE_SEARCH_SYSTEM,
                user=task_user_payload(task, plan),
            )
            return result_from_json(task=task, agent_id=AGENT_ID, data=data)
        except Exception as exc:
            logger.exception("Claude search failed: %s", task)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
