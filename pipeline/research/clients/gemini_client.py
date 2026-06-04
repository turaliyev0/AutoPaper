"""Google Gen AI async client for all research agents."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.logging.gemini import log_request, log_response

from ..config import Settings
from ..schemas import SourceSnippet
from ..utils import extract_json_object
from .base import RETRYABLE, _LlmRetryWait, gemini_error_to_retryable

logger = logging.getLogger(__name__)

T = TypeVar("T")
_GEMINI_FLASH_FALLBACK = "gemini-2.5-flash"


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


def _max_retries(settings: Settings) -> int:
    research = getattr(settings, "research_llm_max_retries", None)
    editor = getattr(settings, "editor_llm_max_retries", None)
    value = research or editor or 8
    return max(3, int(value))


def _flash_fallback_for(model: str) -> str | None:
    name = model.strip().lower()
    if "pro" in name and name != _GEMINI_FLASH_FALLBACK:
        return _GEMINI_FLASH_FALLBACK
    return None


class GeminiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str,
        model: str,
    ) -> None:
        self._settings = settings
        key = api_key.strip()
        if not key:
            raise ValueError("GeminiClient requires a non-empty api_key")
        model_name = model.strip()
        if not model_name:
            raise ValueError("GeminiClient requires a non-empty model")
        self._client = genai.Client(api_key=key)
        self._model = model_name
        self._fallback_model = _flash_fallback_for(model_name)
        self._max_attempts = _max_retries(settings)

    async def _with_retry(
        self,
        label: str,
        fn: Callable[[], Awaitable[T]],
        *,
        model: str | None = None,
    ) -> T:
        from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

        active_model = model or self._model
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self._max_attempts),
            wait=_LlmRetryWait(),
            retry=retry_if_exception_type(RETRYABLE),
            before_sleep=lambda rs: logger.warning(
                "Gemini %s failed on %s (attempt %s/%s): %s",
                label,
                active_model,
                rs.attempt_number,
                self._max_attempts,
                rs.outcome.exception() if rs.outcome else "unknown",
            ),
        ):
            with attempt:
                return await fn()

    async def _call_with_model_fallback(
        self,
        label: str,
        fn: Callable[[str], Awaitable[T]],
    ) -> T:
        try:
            return await self._with_retry(label, lambda: fn(self._model), model=self._model)
        except TimeoutError:
            if not self._fallback_model:
                raise
            logger.warning(
                "Gemini %s still unavailable on %s — retrying with fallback %s",
                label,
                self._model,
                self._fallback_model,
            )
            return await self._with_retry(
                label,
                lambda: fn(self._fallback_model),  # type: ignore[arg-type]
                model=self._fallback_model,
            )

    async def _generate_content(
        self,
        *,
        model: str,
        user: str,
        config: types.GenerateContentConfig,
        trace_label: str,
        mode: str,
    ) -> Any:
        log_request(
            label=trace_label,
            model=model,
            mode=mode,
            user_preview=user,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=user,
                config=config,
            )
        except APIError as exc:
            logger.warning("Gemini API error (%s): %s", model, exc)
            retryable = gemini_error_to_retryable(exc)
            if retryable is not None:
                raise retryable from exc
            raise
        log_response(response, label=trace_label)
        return response

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

        async def _once(model: str) -> dict[str, Any]:
            response = await self._generate_content(
                model=model,
                user=user,
                config=config,
                trace_label=trace_label,
                mode="json",
            )
            text = getattr(response, "text", None) or ""
            return extract_json_object(text)

        return await self._call_with_model_fallback(trace_label, _once)

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

        async def _once(model: str) -> str:
            response = await self._generate_content(
                model=model,
                user=user,
                config=config,
                trace_label=trace_label,
                mode="text",
            )
            return getattr(response, "text", None) or ""

        return await self._call_with_model_fallback(trace_label, _once)

    async def generate_markdown(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "research_index",
    ) -> str:
        return await self.generate_text(system=system, user=user, trace_label=trace_label)

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

        async def _once(model: str) -> tuple[dict[str, Any], list[SourceSnippet]]:
            response = await self._generate_content(
                model=model,
                user=user,
                config=config,
                trace_label="google_search",
                mode="json+google_search",
            )
            text = getattr(response, "text", None) or ""
            if not text.strip():
                raise ValueError("Gemini search returned empty JSON response")
            sources = _sources_from_response(response)
            return extract_json_object(text), sources

        return await self._call_with_model_fallback("google_search", _once)


def gemini_search_client(settings: Settings) -> GeminiClient:
    return GeminiClient(
        settings,
        api_key=settings.gemini_search_api_key,
        model=settings.gemini_search_model,
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
