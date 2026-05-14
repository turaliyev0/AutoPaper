from __future__ import annotations

from typing import Any

import httpx

from autopaper.config import Settings
from autopaper.providers.base import BaseLLMProvider


class GPTProvider(BaseLLMProvider):
    name = "gpt"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
                timeout=120.0,
            )
        return self._client

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        key = self._settings.openai_api_key
        if not key:
            raise RuntimeError("AUTOPAPER_OPENAI_API_KEY is not set")

        body: dict[str, Any] = {
            "model": self._settings.default_model_gpt,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        client = await self._get_client()
        r = await client.post("/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        return str(data["choices"][0]["message"]["content"])

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
