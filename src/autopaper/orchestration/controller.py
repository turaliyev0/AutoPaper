from __future__ import annotations

from dataclasses import dataclass, field

from autopaper.agents import (
    AgentContext,
    CitationAgent,
    ResearchAgent,
    ReviewerAgent,
    ValidationAgent,
    WritingAgent,
)
from autopaper.inputs import PaperDraft, PaperSection, ResearchInput, SectionDraft
from autopaper.providers.base import LLMProvider


@dataclass(slots=True)
class Orchestrator:
    """Runs a fixed multi-stage pipeline; swap LLMs per stage as needed."""

    research_llm: LLMProvider
    writing_llm: LLMProvider
    review_llm: LLMProvider
    title: str = "Untitled Manuscript"
    _sections_order: tuple[PaperSection, ...] = field(
        default=(
            PaperSection.INTRODUCTION,
            PaperSection.RELATED_WORK,
            PaperSection.METHODOLOGY,
            PaperSection.EXPERIMENTS,
            PaperSection.RESULTS,
            PaperSection.DISCUSSION,
            PaperSection.CONCLUSION,
        ),
        repr=False,
    )

    async def run(self, research_input: ResearchInput) -> PaperDraft:
        research = ResearchAgent()
        summary = await research.run(self.research_llm, AgentContext(research_input, []))

        sections: list[SectionDraft] = []

        for ps in self._sections_order:
            writer = WritingAgent(ps.value)
            text = await writer.run(
                self.writing_llm,
                AgentContext(research_input, sections, research_summary=summary),
            )
            sections.append(SectionDraft(ps, text, {}))

        abstract_writer = WritingAgent("abstract (IEEE style, single paragraph preferred)")
        abstract_text = await abstract_writer.run(
            self.writing_llm,
            AgentContext(research_input, sections, research_summary=summary),
        )
        ordered = [SectionDraft(PaperSection.ABSTRACT, abstract_text, {})] + sections

        reviewer = ReviewerAgent()
        peer_review = await reviewer.run(
            self.review_llm, AgentContext(research_input, ordered)
        )

        citation = CitationAgent()
        references_text = await citation.run(
            self.review_llm, AgentContext(research_input, ordered)
        )
        ordered.append(SectionDraft(PaperSection.REFERENCES, references_text, {}))

        validator = ValidationAgent()
        validation_report = await validator.run(
            self.review_llm, AgentContext(research_input, ordered)
        )

        return PaperDraft(
            title=self.title,
            sections=ordered,
            raw_research_summary=summary,
            peer_review_notes=peer_review,
            validation_report=validation_report,
        )
