"""Google Gen AI async client for Gemini search."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from ..config import Settings
from ..utils import extract_json_object
from .base import llm_retry

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._settings = settings
        key = api_key or settings.gemini_search_api_key
        self._client = genai.Client(api_key=key)
        self._model = model or settings.gemini_search_model

    @llm_retry(max_attempts=3)
    async def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.3,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config=config,
            )
        except APIError as exc:
            logger.warning("Gemini API error: %s", exc)
            if getattr(exc, "code", None) in (429, 503):
                raise TimeoutError(str(exc)) from exc
            raise

        text = getattr(response, "text", None) or ""
        return extract_json_object(text)

    @llm_retry(max_attempts=3)
    async def generate_text(self, *, system: str, user: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config=config,
            )
        except APIError as exc:
            if getattr(exc, "code", None) in (429, 503):
                raise TimeoutError(str(exc)) from exc
            raise
        return getattr(response, "text", None) or ""
