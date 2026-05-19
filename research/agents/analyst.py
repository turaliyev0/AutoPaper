"""Report synthesizer — final Markdown from all search agents (Gemini)."""

from __future__ import annotations

import json
import logging

from ..clients.gemini_client import synthesizer_client
from ..config import Settings
from ..manuscript_context import ManuscriptContext
from ..prompts.loader import load_report_synthesizer_instruction
from ..schemas import GatheredResearchBundle, OrchestratorPlan, SynthesisReport

logger = logging.getLogger(__name__)


class ReportSynthesizer:
    def __init__(self, settings: Settings) -> None:
        self._client = synthesizer_client(settings)
        self._system = load_report_synthesizer_instruction()

    async def synthesize(
        self,
        plan: OrchestratorPlan,
        bundle: GatheredResearchBundle,
        *,
        manuscript: ManuscriptContext | None = None,
    ) -> SynthesisReport:
        synth = plan.synthesizer_agent()
        synth_tasks = synth.tasks if synth else []

        user_payload: dict = {
            "research_goal": plan.research_goal.model_dump(),
            "required_outputs": plan.research_goal.required_outputs,
            "synthesizer_tasks": synth_tasks,
            "search_findings": bundle.to_context_dict(),
        }
        if manuscript is not None:
            user_payload["manuscript"] = {
                "summary": manuscript.summary,
                "target_journal": manuscript.target_journal,
                "mismatch_flags": [f.model_dump() for f in manuscript.mismatch_flags],
            }

        markdown = await self._client.generate_markdown(
            system=self._system,
            user=json.dumps(user_payload, indent=2, default=str),
            trace_label="report_synthesizer",
        )
        if not markdown.strip():
            raise ValueError("Report synthesizer returned empty report")

        title = plan.research_goal.main_topic
        logger.info("Report generated (%d chars)", len(markdown))
        return SynthesisReport(title=title, markdown_body=markdown)
