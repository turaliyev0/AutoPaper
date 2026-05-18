"""OpenAI async client for the Orchestrator."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from ..config import Settings
from ..utils import extract_json_object
from .base import llm_retry

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.orchestrator_api_key)
        self._model = settings.orchestrator_model

    async def generate_json(
        self,
        *,
        system: str,
        user: str,
    ) -> dict[str, Any]:
        return await self._generate_json_impl(system=system, user=user)

    @llm_retry(max_attempts=3)
    async def _generate_json_impl(self, *, system: str, user: str) -> dict[str, Any]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            logger.warning("OpenAI API error: %s", exc)
            raise TimeoutError(str(exc)) from exc

        content = response.choices[0].message.content or ""
        return extract_json_object(content)

    async def generate_text(self, *, system: str, user: str) -> str:
        return await self._generate_text_impl(system=system, user=user)

    @llm_retry(max_attempts=3)
    async def _generate_text_impl(self, *, system: str, user: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            raise TimeoutError(str(exc)) from exc
        return response.choices[0].message.content or ""
