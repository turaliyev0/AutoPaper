from __future__ import annotations

from typing import Any

import httpx

from autopaper.config import Settings
from autopaper.providers.base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    name = "claude"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.anthropic.com",
                headers={
                    "x-api-key": self._settings.anthropic_api_key or "",
                    "anthropic-version": "2023-06-01",
                },
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
        key = self._settings.anthropic_api_key
        if not key:
            raise RuntimeError("AUTOPAPER_ANTHROPIC_API_KEY is not set")

        system_parts: list[str] = []
        api_messages: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system_parts.append(m["content"])
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        body: dict[str, Any] = {
            "model": self._settings.default_model_claude,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
            "messages": api_messages,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)

        client = await self._get_client()
        r = await client.post("/v1/messages", json=body)
        r.raise_for_status()
        data = r.json()
        blocks = data.get("content") or []
        texts: list[str] = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                texts.append(str(b.get("text", "")))
        return "".join(texts)

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
