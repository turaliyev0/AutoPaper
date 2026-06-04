"""Runs active search agents in parallel (gemini_search + openai_search)."""

from __future__ import annotations

import asyncio
import logging

from ..config import ACTIVE_SEARCH_AGENT_IDS, Settings
from ..manuscript_context import ManuscriptContext
from ..schemas import GatheredResearchBundle, GatheredTaskResult, OrchestratorPlan
from ..utils import short_step_label
from .search import GeminiSearchAgent, OpenAISearchAgent

logger = logging.getLogger(__name__)

_gemini_semaphore: asyncio.Semaphore | None = None
_gemini_semaphore_limit: int | None = None


def _gemini_limit(settings: Settings | None) -> int:
    if settings is None:
        return 2
    return max(1, int(getattr(settings, "research_gemini_max_concurrent", 2)))


def _get_gemini_semaphore(settings: Settings | None) -> asyncio.Semaphore:
    global _gemini_semaphore, _gemini_semaphore_limit
    limit = _gemini_limit(settings)
    if _gemini_semaphore is None or _gemini_semaphore_limit != limit:
        _gemini_semaphore = asyncio.Semaphore(limit)
        _gemini_semaphore_limit = limit
    return _gemini_semaphore


class SearchCoordinator:
    def __init__(
        self,
        gemini: GeminiSearchAgent,
        openai: OpenAISearchAgent,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._agents = {
            "gemini_search": gemini,
            "openai_search": openai,
        }
        self._settings = settings

    @classmethod
    def from_settings(cls, settings) -> SearchCoordinator:
        return cls(
            GeminiSearchAgent(settings),
            OpenAISearchAgent(settings),
            settings=settings,
        )

    async def gather(
        self,
        plan: OrchestratorPlan,
        *,
        manuscript: ManuscriptContext | None = None,
    ) -> GatheredResearchBundle:
        coros = []
        for target in plan.execution_strategy.target_agents:
            agent_id = target.agent_id
            if agent_id not in ACTIVE_SEARCH_AGENT_IDS:
                logger.debug("Skipping inactive search agent: %s", agent_id)
                continue
            impl = self._agents.get(agent_id)
            if impl is None:
                continue
            for task in target.tasks:
                coros.append(
                    self._run_task_with_progress(
                        impl,
                        agent_id,
                        task,
                        plan,
                        manuscript=manuscript,
                    )
                )

        if not coros:
            raise ValueError(
                "No search tasks in plan. Include gemini_search and/or openai_search."
            )

        logger.info(
            "SearchCoordinator: running %d search tasks (Gemini concurrency=%d)",
            len(coros),
            _gemini_limit(self._settings),
        )
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

    async def _run_task_with_progress(
        self,
        impl: GeminiSearchAgent | OpenAISearchAgent,
        agent_id: str,
        task: str,
        plan: OrchestratorPlan,
        *,
        manuscript: ManuscriptContext | None = None,
    ) -> GatheredTaskResult:
        label = short_step_label(task)
        agent_label = agent_id.replace("_", " ")
        print(f"[STEP] Researching ({agent_label}): {label}", flush=True)
        sem = _get_gemini_semaphore(self._settings)
        try:
            async with sem:
                result = await impl.run_task(task, plan, manuscript=manuscript)
        except Exception:
            print(f"[STEP] Research failed ({agent_label}): {label}", flush=True)
            raise
        if result.success:
            print(f"[STEP] Research complete ({agent_label}): {label}", flush=True)
        else:
            print(f"[STEP] Research failed ({agent_label}): {label}", flush=True)
        return result