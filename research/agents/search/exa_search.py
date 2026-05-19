"""Web search agent (exa_search id) — Gemini + Google Search grounding."""

from __future__ import annotations

import logging

from ...clients.gemini_client import search_client
from ...config import Settings
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import RESEARCH_TASK_JSON_SYSTEM, failed_result, result_from_json

logger = logging.getLogger(__name__)

AGENT_ID = "exa_search"

EXA_SEARCH_SYSTEM = (
    RESEARCH_TASK_JSON_SYSTEM
    + "\nUse Google Search grounding to find current public web information. "
    "Include real URLs only when returned by search grounding. "
    "If no sources are found, state that in limitations."
)


class ExaSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._client = search_client(settings, role="exa_search")

    async def run_task(self, task: str, plan: OrchestratorPlan) -> GatheredTaskResult:
        try:
            query = (
                f"{plan.research_goal.main_topic}. {task}. "
                f"Focus: {', '.join(plan.research_goal.required_outputs)}"
            )
            data, sources = await self._client.generate_json_with_google_search(
                system=EXA_SEARCH_SYSTEM,
                user=query,
            )
            if sources and not data.get("key_points"):
                data["key_points"] = [f"{s.title}: {s.url}" for s in sources[:10]]
            return result_from_json(
                task=task,
                agent_id=AGENT_ID,
                data=data,
                sources=sources,
            )
        except Exception as exc:
            logger.exception("Gemini web search (exa_search slot) failed: %s", task)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
