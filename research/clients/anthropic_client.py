"""Anthropic async client for Claude search and report synthesis."""

from __future__ import annotations

import logging
from typing import Any

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic, RateLimitError

from ..config import Settings
from ..utils import extract_json_object
from .base import llm_retry

logger = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._settings = settings
        key = api_key or settings.report_synthesizer_api_key
        self._client = AsyncAnthropic(api_key=key)
        self._model = model or settings.report_synthesizer_model

    @llm_retry(max_attempts=3)
    async def generate_markdown(self, *, system: str, user: str) -> str:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.4,
            )
        except (RateLimitError, APIConnectionError) as exc:
            logger.warning("Anthropic connection/rate error: %s", exc)
            raise TimeoutError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code in (429, 529):
                raise TimeoutError(str(exc)) from exc
            raise

        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    @llm_retry(max_attempts=3)
    async def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        text = await self.generate_markdown(
            system=system + "\n\nReply with only one valid JSON object (no markdown fences).",
            user=user,
        )
        return extract_json_object(text)
