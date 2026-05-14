from __future__ import annotations

import json
from typing import Any

import httpx

from autopaper.config import Settings
from autopaper.providers.base import BaseLLMProvider


def _extract_text_from_gemini(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    return "".join(texts)


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        key = self._settings.google_api_key
        if not key:
            raise RuntimeError("AUTOPAPER_GOOGLE_API_KEY is not set")

        model = self._settings.default_model_gemini
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={key}"
        )
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = "user" if m["role"] != "assistant" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = max_tokens

        client = await self._get_client()
        r = await client.post(
            url, content=json.dumps(body), headers={"Content-Type": "application/json"}
        )
        r.raise_for_status()
        return _extract_text_from_gemini(r.json())

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
