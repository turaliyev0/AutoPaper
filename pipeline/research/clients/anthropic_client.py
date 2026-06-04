"""Anthropic async client for evaluation agents (JSON rubric responses)."""

from __future__ import annotations

import logging
from typing import Any

from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    RateLimitError,
)

from backend.logging.anthropic import log_anthropic_request, log_anthropic_response

from ..config import Settings
from ..utils import extract_json_object
from .base import llm_retry

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 8192


class AnthropicClient:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str,
        model: str,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._settings = settings
        key = api_key.strip()
        if not key:
            raise ValueError("AnthropicClient requires a non-empty api_key")
        model_name = model.strip()
        if not model_name:
            raise ValueError("AnthropicClient requires a non-empty model")
        self._client = AsyncAnthropic(api_key=key)
        self._model = model_name
        self._max_tokens = max_tokens

    @llm_retry(max_attempts=3)
    async def generate_json(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_json",
    ) -> dict[str, Any]:
        log_anthropic_request(
            label=trace_label,
            model=self._model,
            mode="json",
            user_preview=user,
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.2,
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            logger.warning("Anthropic API error: %s", exc)
            raise TimeoutError(str(exc)) from exc

        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        content = "".join(parts)
        log_anthropic_response(label=trace_label, content=content)
        return extract_json_object(content)

    @llm_retry(max_attempts=3)
    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_text",
    ) -> str:
        log_anthropic_request(
            label=trace_label,
            model=self._model,
            mode="text",
            user_preview=user,
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.3,
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            raise TimeoutError(str(exc)) from exc

        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        content = "".join(parts)
        log_anthropic_response(label=trace_label, content=content)
        return content
