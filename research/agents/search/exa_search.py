"""Exa search agent — live web search (deep + highlights) per subtask."""

from __future__ import annotations

import logging

from ...clients.exa_client import ExaClient
from ...config import Settings
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import failed_result, result_from_json

logger = logging.getLogger(__name__)

AGENT_ID = "exa_search"


class ExaSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._client = ExaClient(settings)

    async def run_task(self, task: str, plan: OrchestratorPlan) -> GatheredTaskResult:
        try:
            query = (
                f"{plan.research_goal.main_topic}. {task}. "
                f"Focus: {', '.join(plan.research_goal.required_outputs)}"
            )
            sources, exa_summary = await self._client.search(query)
            data = {
                "summary": exa_summary or f"Exa returned {len(sources)} sources.",
                "key_points": [f"{s.title}: {s.url}" for s in sources[:10]],
                "confidence": "high" if sources else "low",
                "limitations": "Live web via Exa only; synthesis may omit undisplayed pages.",
            }
            return result_from_json(
                task=task,
                agent_id=AGENT_ID,
                data=data,
                sources=sources,
            )
        except Exception as exc:
            logger.exception("Exa search failed: %s", task)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
