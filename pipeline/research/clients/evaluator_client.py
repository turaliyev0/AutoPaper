"""Anthropic clients for evaluation agents (research validator + manuscript QA)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..config import Settings
from .anthropic_client import AnthropicClient


@runtime_checkable
class JsonLlmClient(Protocol):
    async def generate_json(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_json",
    ) -> dict[str, Any]: ...


def research_validator_client(settings: Settings) -> AnthropicClient:
    return AnthropicClient(
        settings,
        api_key=settings.research_validator_api_key,
        model=settings.research_validator_model,
    )


def manuscript_qa_client(settings) -> AnthropicClient:
    """EditorSettings or any object with manuscript_qa_api_key + manuscript_qa_model."""
    return AnthropicClient(
        settings,
        api_key=settings.manuscript_qa_api_key,
        model=settings.manuscript_qa_model,
    )
