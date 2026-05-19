"""Runs active search agents in parallel (gemini_search + openai_search)."""

from __future__ import annotations

import asyncio
import logging

from ..config import ACTIVE_SEARCH_AGENT_IDS
from ..manuscript_context import ManuscriptContext
from ..schemas import GatheredResearchBundle, GatheredTaskResult, OrchestratorPlan
from .search import GeminiSearchAgent, OpenAISearchAgent

logger = logging.getLogger(__name__)

_LEGACY_SEARCH_IDS: dict[str, str] = {
    "gemini_explorer": "gemini_search",
}


class SearchCoordinator:
    def __init__(
        self,
        gemini: GeminiSearchAgent,
        openai: OpenAISearchAgent,
    ) -> None:
        self._agents = {
            "gemini_search": gemini,
            "openai_search": openai,
        }

    @classmethod
    def from_settings(cls, settings) -> SearchCoordinator:
        return cls(
            GeminiSearchAgent(settings),
            OpenAISearchAgent(settings),
        )

    async def gather(
        self,
        plan: OrchestratorPlan,
        *,
        manuscript: ManuscriptContext | None = None,
    ) -> GatheredResearchBundle:
        coros = []
        for target in plan.execution_strategy.target_agents:
            agent_id = _LEGACY_SEARCH_IDS.get(target.agent_id, target.agent_id)
            if agent_id not in ACTIVE_SEARCH_AGENT_IDS:
                if agent_id in {"claude_search", "exa_search"}:
                    logger.debug("Skipping disabled search agent: %s", agent_id)
                continue
            impl = self._agents.get(agent_id)
            if impl is None:
                continue
            for task in target.tasks:
                coros.append(impl.run_task(task, plan, manuscript=manuscript))

        if not coros:
            raise ValueError(
                "No search tasks in plan. Include gemini_search and/or openai_search."
            )

        logger.info("SearchCoordinator: running %d search tasks in parallel", len(coros))
        raw = await asyncio.gather(*coros, return_exceptions=True)

        results: list[GatheredTaskResult] = []
        for item in raw:
            if isinstance(item, BaseException):
                logger.exception("Search task crashed: %s", item)
                results.append(
                    GatheredTaskResult(
                        task="unknown",
                        agent_id="unknown",
                        success=False,
                        error=str(item),
                    ),
                )
            else:
                results.append(item)

        bundle = GatheredResearchBundle(plan=plan, results=results)
        ok = len(bundle.successful_results)
        logger.info("Search complete: %d/%d tasks succeeded", ok, len(results))
        return bundle
