from __future__ import annotations

from autopaper.providers.base import BaseLLMProvider


class StubLLMProvider(BaseLLMProvider):
    """Placeholder LLM until a real provider is configured."""

    name = "stub"

    def __init__(self, *, reply: str | None = None) -> None:
        self._reply = reply or (
            "[stub LLM] Configure a real provider (e.g. GPT, Claude, Gemini) and wire it in cli.py."
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        return self._reply

    async def aclose(self) -> None:
        return None
