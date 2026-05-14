from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol


class LLMProvider(Protocol):
    """Unified async surface for any chat-capable model."""

    name: str

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """Return assistant text for the given message list."""
        ...


class BaseLLMProvider(ABC):
    """Optional ABC for shared helpers."""

    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str: ...
