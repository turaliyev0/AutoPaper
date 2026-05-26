"""Editor orchestrator — plans the IEEE manuscript structure via OpenAI Responses API."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from pipeline.research.clients.openai_client import OpenAIClient

from ..config import EditorSettings
from ..context import EditorContext
from ..prompts.loader import load_editor_orchestrator_instruction
from ..schemas import EditorPlan
from .orchestrator_tools import EDITOR_TOOL_SCHEMAS, EditorPlanBuilder

logger = logging.getLogger(__name__)


class EditorOrchestratorAgent:
    """
    Uses the same OpenAI Responses API tool-session loop as the research orchestrator.

    Receives :class:`EditorContext` and produces a sealed :class:`EditorPlan`
    written to ``09_editor_plan.json``.
    """

    def __init__(self, client: OpenAIClient, *, settings: EditorSettings) -> None:
        self._client = client
        self._settings = settings

    async def create_plan(self, context: EditorContext) -> EditorPlan:
        system = load_editor_orchestrator_instruction()
        user_prompt = (
            "Create an IEEE manuscript editing plan from the following context.\n\n"
            "Use the tools in order:\n"
            "1. set_document_goal — title, format, required sections\n"
            "2. map_section_sources — once per section\n"
            "3. delegate_figure — once per figure\n"
            "4. set_validation_focus\n"
            "5. finalize_editor_plan\n\n"
            "--- CONTEXT ---\n"
            f"{context.to_orchestrator_block()}"
        )

        builder = EditorPlanBuilder()
        await self._client.run_tool_session(
            system=system,
            user=user_prompt,
            tools=EDITOR_TOOL_SCHEMAS,
            tool_handlers=builder.tool_handlers(),
        )

        if not builder.is_complete():
            missing_parts: list[str] = []
            if not builder.article_title:
                missing_parts.append("set_document_goal not called")
            if not builder.section_specs:
                missing_parts.append("no sections mapped via map_section_sources")
            raise ValueError(
                "Editor orchestrator did not complete the plan. "
                + "; ".join(missing_parts)
            )

        try:
            plan = builder.to_plan()
            EditorPlan.model_validate(plan.model_dump())
        except (ValidationError, ValueError) as exc:
            logger.error("Editor plan failed validation: %s", exc)
            raise ValueError(f"Editor orchestrator produced invalid plan: {exc}") from exc

        logger.info(
            "Editor plan: title=%r, sections=%d, figures=%d",
            plan.article_title,
            len(plan.sections),
            len(plan.figures),
        )
        return plan
