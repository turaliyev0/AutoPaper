"""Report synthesizer — final Markdown from all search agents."""

from __future__ import annotations

import json
import logging

from ..clients.anthropic_client import AnthropicClient
from ..config import Settings
from ..schemas import GatheredResearchBundle, OrchestratorPlan, SynthesisReport

logger = logging.getLogger(__name__)

SYNTHESIZER_SYSTEM = """You are a senior report synthesizer. You receive findings from multiple search agents:
- gemini_search (model knowledge)
- claude_search (model knowledge)
- exa_search (live web with URLs and highlights)

Write a polished Markdown report that:
- Addresses every item in required_outputs
- Cross-checks agents: note agreement and contradictions
- Cites Exa sources inline as [title](url) when used
- States limitations (failed tasks, knowledge cutoff, Exa coverage)
- Does not mention JSON, orchestrator, or pipeline mechanics

Output Markdown only."""


class ReportSynthesizer:
    def __init__(self, settings: Settings) -> None:
        self._client = AnthropicClient(
            settings,
            api_key=settings.report_synthesizer_api_key,
            model=settings.report_synthesizer_model,
        )

    async def synthesize(
        self,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
    ) -> SynthesisReport:
        synth = plan.synthesizer_agent()
        synth_tasks = synth.tasks if synth else []

        user_payload = {
            "orchestrator_config": plan.orchestrator_config.model_dump(),
            "research_goal": plan.research_goal.model_dump(),
            "synthesizer_tasks": synth_tasks,
            "search_findings": bundle.to_context_dict(),
        }
        markdown = await self._client.generate_markdown(
            system=SYNTHESIZER_SYSTEM,
            user=json.dumps(user_payload, indent=2, default=str),
        )
        if not markdown.strip():
            raise ValueError("Report synthesizer returned empty report")

        title = plan.research_goal.main_topic
        logger.info("Report generated (%d chars)", len(markdown))
        return SynthesisReport(title=title, markdown_body=markdown)
