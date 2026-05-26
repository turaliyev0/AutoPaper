"""Editor orchestrator — plans the IEEE manuscript structure via OpenAI Responses API."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from pipeline.research.clients.openai_client import OpenAIClient

from ..config import EditorSettings
from ..context import EditorContext
from ..plan_validate import collect_plan_validation_errors
from ..prompts.loader import load_editor_orchestrator_instruction
from ..schemas import EditorPlan
from .orchestrator_tools import EDITOR_TOOL_SCHEMAS, EditorPlanBuilder

logger = logging.getLogger(__name__)

_EDITOR_MAX_TOOL_TURNS = 30
_EDITOR_PLAN_ATTEMPTS = 3


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
            "You are the process supervisor: use the Research index and Research catalog "
            "(summary excerpts) to assign each trusted slug to exactly ONE section.\n\n"
            "Use the tools in this order:\n"
            "1. set_document_goal — title, format, required sections\n"
            "2. map_section_sources — once per section (manuscript_parts; slugs optional here)\n"
            "3. assign_research_slug — **once per trusted slug** in the catalog\n"
            "4. delegate_figure — primary_sections required on each figure\n"
            "5. set_validation_focus\n"
            "6. finalize_editor_plan — only when every slug is assigned\n\n"
            "--- CONTEXT ---\n"
            f"{context.to_orchestrator_block()}"
        )

        builder = EditorPlanBuilder(
            trusted_slugs=frozenset(a.slug for a in context.trusted_artifacts),
        )
        input_items: list[dict] | None = None
        user_msg = user_prompt
        last_errors: list[str] = []

        for attempt in range(_EDITOR_PLAN_ATTEMPTS):
            input_items = await self._client.run_tool_session(
                system=system,
                user=user_msg,
                tools=EDITOR_TOOL_SCHEMAS,
                tool_handlers=builder.tool_handlers(),
                max_turns=_EDITOR_MAX_TOOL_TURNS,
                input_items=input_items,
            )

            if not builder.is_complete():
                missing_parts: list[str] = []
                if not builder.article_title:
                    missing_parts.append("set_document_goal not called")
                if not builder.section_specs:
                    missing_parts.append("no sections mapped via map_section_sources")
                if builder._unassigned_slugs():
                    missing_parts.append(
                        "unassigned slugs: " + ", ".join(builder._unassigned_slugs())
                    )
                last_errors = missing_parts
                if attempt < _EDITOR_PLAN_ATTEMPTS - 1:
                    builder._finalized = False
                    user_msg = (
                        "Plan incomplete. Fix with tools only:\n- "
                        + "\n- ".join(missing_parts)
                        + "\n\nCall assign_research_slug for each catalog slug, "
                        "then finalize_editor_plan."
                    )
                    continue
                raise ValueError(
                    "Editor orchestrator did not complete the plan. "
                    + "; ".join(missing_parts)
                )

            try:
                plan = builder.to_plan()
                EditorPlan.model_validate(plan.model_dump())
                plan_errors = collect_plan_validation_errors(plan, context)
                if plan_errors:
                    raise ValueError(
                        "Editor plan validation failed:\n- " + "\n- ".join(plan_errors)
                    )
            except (ValidationError, ValueError) as exc:
                last_errors = [str(exc)]
                logger.warning(
                    "Editor plan attempt %d/%d failed: %s",
                    attempt + 1,
                    _EDITOR_PLAN_ATTEMPTS,
                    exc,
                )
                if attempt >= _EDITOR_PLAN_ATTEMPTS - 1:
                    raise ValueError(
                        f"Editor orchestrator produced invalid plan: {exc}"
                    ) from exc
                builder._finalized = False
                user_msg = (
                    f"Plan validation failed (attempt {attempt + 1}). Fix with tools only:\n"
                    f"{exc}\n\n"
                    "Use assign_research_slug for each missing slug, then finalize_editor_plan."
                )
                continue

            logger.info(
                "Editor plan: title=%r, sections=%d, figures=%d (attempt %d)",
                plan.article_title,
                len(plan.sections),
                len(plan.figures),
                attempt + 1,
            )
            return plan

        raise ValueError(
            "Editor orchestrator produced invalid plan: " + "; ".join(last_errors)
        )
