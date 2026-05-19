"""Second Gemini search agent (claude_search id) — critical / methods angle."""

from __future__ import annotations

import logging

from ...clients.gemini_client import search_client
from ...config import Settings
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import RESEARCH_TASK_JSON_SYSTEM, failed_result, result_from_json, task_user_payload

logger = logging.getLogger(__name__)

AGENT_ID = "claude_search"

CLAUDE_SEARCH_SYSTEM = (
    RESEARCH_TASK_JSON_SYSTEM
    + "\nYou are the critical-angle researcher: emphasize methods, limitations, "
    "contradictions, and gaps. Use model knowledge only (no live web). Do not invent URLs."
)


class ClaudeSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._client = search_client(settings, role="claude_search")

    async def run_task(self, task: str, plan: OrchestratorPlan) -> GatheredTaskResult:
        try:
            data = await self._client.generate_json(
                system=CLAUDE_SEARCH_SYSTEM,
                user=task_user_payload(task, plan),
            )
            return result_from_json(task=task, agent_id=AGENT_ID, data=data)
        except Exception as exc:
            logger.exception("Gemini search (claude_search slot) failed: %s", task)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
