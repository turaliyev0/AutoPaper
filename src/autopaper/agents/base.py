from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from autopaper.inputs import ResearchInput, SectionDraft
from autopaper.providers.base import LLMProvider


@dataclass(slots=True)
class AgentContext:
    research_input: ResearchInput
    prior_sections: list[SectionDraft]
    research_summary: str | None = None


class Agent(ABC):
    """Single step in the paper pipeline; implementations call one or more LLMs."""

    role: str = "agent"

    @abstractmethod
    async def run(self, llm: LLMProvider, ctx: AgentContext) -> str: ...
