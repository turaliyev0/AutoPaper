"""Orchestrator agent (GPT-4o): plans and emits validated JSON delegation config."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from ..clients.openai_client import OpenAIClient
from ..schemas import OrchestratorPlan, SEARCH_AGENT_IDS

logger = logging.getLogger(__name__)

ORCHESTRATOR_SYSTEM = """You are SearchOrchestrator, a senior research project manager.
Given a user's research goal, output ONLY a single JSON object matching this exact structure:

{
  "orchestrator_config": {
    "agent_name": "SearchOrchestrator",
    "mode": "parallel_subtasking",
    "allow_cross_model_validation": true
  },
  "research_goal": {
    "main_topic": "<concise topic>",
    "required_outputs": ["<output 1>", "<output 2>", "..."]
  },
  "execution_strategy": {
    "action": "separate_into_subtopics",
    "target_agents": [
      {
        "agent_id": "gemini_search",
        "model": "gemini-2.0-flash",
        "tasks": ["<subtopic for Gemini model knowledge>", "..."]
      },
      {
        "agent_id": "claude_search",
        "model": "claude-3-5-sonnet",
        "tasks": ["<subtopic for Claude model knowledge>", "..."]
      },
      {
        "agent_id": "exa_search",
        "model": "exa-deep",
        "tasks": ["<web search query for Exa — clear, specific>", "..."]
      },
      {
        "agent_id": "report_synthesizer",
        "model": "claude-3-5-sonnet",
        "tasks": ["Synthesize all search agent findings into one final Markdown report"]
      }
    ]
  }
}

Rules:
- Always include all four agents: gemini_search, claude_search, exa_search, report_synthesizer.
- gemini_search / claude_search: 2–4 subtasks each (research angles, not duplicate wording).
- exa_search: 2–4 web search queries (short, Exa-ready strings).
- report_synthesizer: 1–2 tasks describing final report synthesis only (no searching).
- No markdown fences. No commentary outside JSON.
"""


class OrchestratorAgent:
    def __init__(self, client: OpenAIClient) -> None:
        self._client = client

    async def create_plan(self, research_goal: str) -> OrchestratorPlan:
        user_prompt = (
            "Research goal from the user:\n\n"
            f"{research_goal.strip()}\n\n"
            "Produce the orchestrator JSON configuration."
        )
        raw = await self._client.generate_json(system=ORCHESTRATOR_SYSTEM, user=user_prompt)
        try:
            plan = OrchestratorPlan.model_validate(raw)
        except ValidationError as exc:
            logger.error("Orchestrator JSON failed validation: %s", exc)
            logger.debug("Raw orchestrator payload: %s", json.dumps(raw, indent=2))
            raise ValueError(f"Orchestrator produced invalid plan: {exc}") from exc
        search_count = sum(
            1
            for a in plan.execution_strategy.target_agents
            if a.agent_id in SEARCH_AGENT_IDS or a.agent_id == "gemini_explorer"
        )
        logger.info(
            "Orchestrator plan: topic=%r, search_agents=%d",
            plan.research_goal.main_topic,
            search_count,
        )
        return plan
