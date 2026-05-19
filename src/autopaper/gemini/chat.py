"""Stateful multi-turn Gemini chat (SDK ``client.chats.create``)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from google import genai
from google.genai import types


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text and str(text).strip():
        return str(text)
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if part_text and str(part_text).strip():
                return str(part_text)
    return ""


class GeminiChat:
    """
  Multi-turn chat with automatic history (Gemini "Chats" API).

  Use this when the model must remember prior turns in the same run.
  For one-shot JSON agents, keep using ``generate_content``.
  """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system_instruction: str | None = None,
        config: types.GenerateContentConfig | None = None,
        history: list[types.Content] | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        base = config or types.GenerateContentConfig()
        if system_instruction and not base.system_instruction:
            base = base.model_copy(update={"system_instruction": system_instruction})
        self._config = base
        self._chat = self._client.chats.create(
            model=model,
            config=self._config,
            history=history,
        )

    @property
    def history(self) -> list[Any]:
        return list(getattr(self._chat, "history", None) or [])

    def send(self, message: str) -> str:
        response = self._chat.send_message(message)
        return _response_text(response)

    def send_stream(self, message: str) -> Iterator[str]:
        for chunk in self._chat.send_message_stream(message):
            text = getattr(chunk, "text", None)
            if text:
                yield str(text)


class AsyncGeminiChat:
    """Async variant of :class:`GeminiChat`."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system_instruction: str | None = None,
        config: types.GenerateContentConfig | None = None,
        history: list[types.Content] | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        base = config or types.GenerateContentConfig()
        if system_instruction and not base.system_instruction:
            base = base.model_copy(update={"system_instruction": system_instruction})
        self._config = base
        self._chat = self._client.aio.chats.create(
            model=model,
            config=self._config,
            history=history,
        )

    @property
    def history(self) -> list[Any]:
        return list(getattr(self._chat, "history", None) or [])

    async def send(self, message: str) -> str:
        response = await self._chat.send_message(message)
        return _response_text(response)

    async def send_stream(self, message: str) -> AsyncIterator[str]:
        stream = await self._chat.send_message_stream(message)
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield str(text)
