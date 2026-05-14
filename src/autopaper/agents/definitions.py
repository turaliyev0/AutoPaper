from __future__ import annotations

from autopaper.agents.base import Agent, AgentContext
from autopaper.providers.base import LLMProvider


class ResearchAgent(Agent):
    role = "research"

    async def run(self, llm: LLMProvider, ctx: AgentContext) -> str:
        ri = ctx.research_input
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research analyst. Synthesize the user's materials into "
                    "structured bullet points: objectives, methods, datasets, metrics, "
                    "key results, limitations, and open questions. Be faithful to the source; "
                    "do not invent citations or numbers."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User instructions:\n{ri.user_instructions}\n\n"
                    f"Research notes:\n{ri.notes}\n\n"
                    f"Model outputs / results:\n{ri.model_outputs or '(none)'}\n\n"
                    f"Technical / architecture details:\n{ri.technical_details or '(none)'}"
                ),
            },
        ]
        return await llm.complete(messages, temperature=0.2)


class WritingAgent(Agent):
    role = "writing"

    def __init__(self, section: str) -> None:
        self._section = section

    async def run(self, llm: LLMProvider, ctx: AgentContext) -> str:
        synth = ctx.research_summary or ""
        if not synth and ctx.prior_sections:
            synth = ctx.prior_sections[0].content
        prior = "\n\n".join(f"## {s.section.value}\n{s.content}" for s in ctx.prior_sections)
        ri = ctx.research_input
        messages = [
            {
                "role": "system",
                "content": (
                    "You write IEEE-style technical prose for a single section. "
                    "Use clear subsection headings where appropriate. "
                    "Do not fabricate references; use \\cite{placeholder} if a citation is needed."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write the section: {self._section}\n\n"
                    f"Research synthesis:\n{synth}\n\n"
                    f"Already drafted sections:\n{prior or '(none)'}\n\n"
                    f"Original instructions:\n{ri.user_instructions}"
                ),
            },
        ]
        return await llm.complete(messages, temperature=0.35)


class ReviewerAgent(Agent):
    role = "reviewer"

    async def run(self, llm: LLMProvider, ctx: AgentContext) -> str:
        body = "\n\n".join(f"## {s.section.value}\n{s.content}" for s in ctx.prior_sections)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict peer reviewer. List concrete issues: clarity, structure, "
                    "missing definitions, inconsistent notation, unsupported claims, and "
                    "formatting problems vs IEEE conventions. End with prioritized revision bullets."
                ),
            },
            {"role": "user", "content": body},
        ]
        return await llm.complete(messages, temperature=0.2)


class CitationAgent(Agent):
    role = "citation"

    async def run(self, llm: LLMProvider, ctx: AgentContext) -> str:
        body = "\n\n".join(f"## {s.section.value}\n{s.content}" for s in ctx.prior_sections)
        messages = [
            {
                "role": "system",
                "content": (
                    "You normalize citations and reference placeholders for IEEE LaTeX. "
                    "Output only: (1) a cleaned Related Work / References paragraph block, "
                    "and (2) a BibTeX stub list for each distinct work mentioned, using keys "
                    "author_year when possible. If information is missing, say UNKNOWN rather than guessing."
                ),
            },
            {"role": "user", "content": body},
        ]
        return await llm.complete(messages, temperature=0.1)


class ValidationAgent(Agent):
    role = "validation"

    async def run(self, llm: LLMProvider, ctx: AgentContext) -> str:
        body = "\n\n".join(f"## {s.section.value}\n{s.content}" for s in ctx.prior_sections)
        messages = [
            {
                "role": "system",
                "content": (
                    "Check internal consistency: terminology, symbols, claimed contributions vs results, "
                    "and whether conclusions match the evidence in the draft. "
                    "Flag anything that looks like hallucinated metrics or citations."
                ),
            },
            {"role": "user", "content": body},
        ]
        return await llm.complete(messages, temperature=0.1)
