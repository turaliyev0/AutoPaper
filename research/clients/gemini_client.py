"""Google Gen AI async client for all research agents."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from autopaper.gemini.trace import log_request, log_response

from ..config import Settings
from ..schemas import SourceSnippet
from ..utils import extract_json_object
from .base import llm_retry

logger = logging.getLogger(__name__)


def _sources_from_response(response: Any) -> list[SourceSnippet]:
    snippets: list[SourceSnippet] = []
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return snippets
    meta = getattr(candidates[0], "grounding_metadata", None)
    if not meta:
        return snippets
    for chunk in getattr(meta, "grounding_chunks", None) or []:
        web = getattr(chunk, "web", None)
        if not web:
            continue
        url = (getattr(web, "uri", None) or getattr(web, "url", None) or "").strip()
        title = (getattr(web, "title", None) or "").strip()
        if url:
            snippets.append(SourceSnippet(url=url, title=title, excerpt=""))
    return snippets


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
        self._model = model or settings.default_gemini_model

    @llm_retry(max_attempts=3)
    async def generate_json(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_json",
    ) -> dict[str, Any]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.2,
        )
        log_request(
            label=trace_label,
            model=self._model,
            mode="json",
            user_preview=user,
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

        log_response(response, label=trace_label)
        text = getattr(response, "text", None) or ""
        return extract_json_object(text)

    @llm_retry(max_attempts=3)
    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_text",
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
        )
        log_request(
            label=trace_label,
            model=self._model,
            mode="text",
            user_preview=user,
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
        log_response(response, label=trace_label)
        return getattr(response, "text", None) or ""

    async def generate_markdown(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "research_index",
    ) -> str:
        return await self.generate_text(system=system, user=user, trace_label=trace_label)

    @llm_retry(max_attempts=3)
    async def generate_json_with_google_search(
        self,
        *,
        system: str,
        user: str,
    ) -> tuple[dict[str, Any], list[SourceSnippet]]:
        """Structured JSON research using Gemini + Google Search grounding."""
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.2,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
        log_request(
            label="google_search",
            model=self._model,
            mode="json+google_search",
            tools=["google_search"],
            user_preview=user,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config=config,
            )
        except APIError as exc:
            logger.warning("Gemini search grounding error: %s", exc)
            if getattr(exc, "code", None) in (429, 503):
                raise TimeoutError(str(exc)) from exc
            raise

        log_response(response, label="google_search")
        text = getattr(response, "text", None) or ""
        if not text.strip():
            raise ValueError("Gemini search returned empty JSON response")
        sources = _sources_from_response(response)
        return extract_json_object(text), sources


def gemini_search_client(settings: Settings) -> GeminiClient:
    return GeminiClient(
        settings,
        api_key=settings.gemini_search_api_key,
        model=settings.gemini_search_model,
    )


def validator_client(settings: Settings) -> GeminiClient:
    return GeminiClient(
        settings,
        api_key=settings.research_validator_api_key,
        model=settings.research_validator_model,
    )


def index_client(settings: Settings) -> GeminiClient:
    return GeminiClient(
        settings,
        api_key=settings.research_index_api_key,
        model=settings.research_index_model,
    )


def openai_search_client(settings: Settings) -> GeminiClient:
    """Critique/methods search agent (agent_id openai_search) — Gemini at runtime."""
    return GeminiClient(
        settings,
        api_key=settings.openai_search_api_key,
        model=settings.openai_search_model,
    )


def orchestrator_followup_client(settings: Settings) -> GeminiClient:
    """Post-validation follow-up refinement (second orchestrator call)."""
    return GeminiClient(
        settings,
        api_key=settings.gemini_search_api_key,
        model=settings.gemini_search_model,
    )
