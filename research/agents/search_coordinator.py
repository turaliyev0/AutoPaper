"""Runs all search agents (Gemini, Claude, Exa) in parallel."""

from __future__ import annotations

import asyncio
import logging

from ..schemas import GatheredResearchBundle, GatheredTaskResult, OrchestratorPlan
from .search import (
    SEARCH_AGENT_IDS,
    ClaudeSearchAgent,
    ExaSearchAgent,
    GeminiSearchAgent,
)

logger = logging.getLogger(__name__)

# Orchestrator legacy id → current search agent id
_LEGACY_SEARCH_IDS: dict[str, str] = {
    "gemini_explorer": "gemini_search",
}

_SEARCH_IMPL = {
    "gemini_search": GeminiSearchAgent,
    "claude_search": ClaudeSearchAgent,
    "exa_search": ExaSearchAgent,
}


class SearchCoordinator:
    def __init__(
        self,
        gemini: GeminiSearchAgent,
        claude: ClaudeSearchAgent,
        exa: ExaSearchAgent,
    ) -> None:
        self._agents = {
            "gemini_search": gemini,
            "claude_search": claude,
            "exa_search": exa,
        }

    @classmethod
    def from_settings(cls, settings) -> SearchCoordinator:
        return cls(
            GeminiSearchAgent(settings),
            ClaudeSearchAgent(settings),
            ExaSearchAgent(settings),
        )

    async def gather(self, plan: OrchestratorPlan) -> GatheredResearchBundle:
        coros = []
        for target in plan.execution_strategy.target_agents:
            agent_id = _LEGACY_SEARCH_IDS.get(target.agent_id, target.agent_id)
            if agent_id not in SEARCH_AGENT_IDS:
                continue
            impl = self._agents[agent_id]
            for task in target.tasks:
                coros.append(impl.run_task(task, plan))

        if not coros:
            raise ValueError(
                "No search tasks in plan. Include gemini_search, claude_search, and/or exa_search."
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
