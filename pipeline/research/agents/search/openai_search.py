"""Critique/methods search agent (agent_id openai_search) — OpenAI or Gemini per config."""

from __future__ import annotations

import logging
from typing import Any

from ...clients.gemini_client import GeminiClient, openai_search_client
from ...clients.openai_client import OpenAIClient
from ...config import Settings
from ...prompts.loader import load_openai_search_instruction
from ...manuscript_context import ManuscriptContext
from ...schemas import GatheredTaskResult, OrchestratorPlan
from .base import failed_result, result_from_json, task_user_payload

logger = logging.getLogger(__name__)

AGENT_ID = "openai_search"


class OpenAISearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._system = load_openai_search_instruction()
        if settings.openai_search_uses_openai:
            self._client: Any = OpenAIClient(
                settings,
                api_key=settings.orchestrator_api_key,
                model=settings.openai_search_model,
            )
            self._backend = "openai"
        else:
            self._client = openai_search_client(settings)
            self._backend = "gemini"

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
                trace_label=f"openai_search:{task[:48]}",
            )
            return result_from_json(task=task, agent_id=AGENT_ID, data=data)
        except Exception as exc:
            logger.exception("%s search failed: %s", self._backend, exc)
            return failed_result(task=task, agent_id=AGENT_ID, error=str(exc))
