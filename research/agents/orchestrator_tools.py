"""OpenAI function-calling tools that build an :class:`OrchestratorPlan`."""

from __future__ import annotations

import json
from typing import Any, Callable

from ..config import Settings
from ..schemas import (
    ExecutionStrategy,
    OrchestratorConfig,
    OrchestratorPlan,
    ResearchGoal,
    TargetAgent,
)

# OpenAI Chat Completions tool schemas (function calling).
ORCHESTRATOR_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_research_goal",
            "description": (
                "Set the main research topic and concrete deliverables the final report must cover."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "main_topic": {
                        "type": "string",
                        "description": "Concise topic string.",
                    },
                    "required_outputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3–6 required report sections or questions.",
                        "minItems": 1,
                    },
                },
                "required": ["main_topic", "required_outputs"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_gemini_search",
            "description": (
                "Assign 2–4 background/literature subtasks to gemini_search (distinct wording)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 6,
                    },
                },
                "required": ["tasks"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_openai_search",
            "description": (
                "Assign 2–4 methods/limitations/comparison subtasks to openai_search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 6,
                    },
                },
                "required": ["tasks"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_research_validation",
            "description": (
                "Assign 1–3 validation focus areas for research_validator "
                "(source traceability and summary clarity per search task; no new searching)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 3,
                    },
                },
                "required": ["tasks"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_orchestrator_plan",
            "description": (
                "Mark delegation complete after all prior tools were called. "
                "The runtime builds the validated JSON plan from tool state."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]


class OrchestratorPlanBuilder:
    """Mutable plan state updated by orchestrator tool calls."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.main_topic: str = ""
        self.required_outputs: list[str] = []
        self.gemini_tasks: list[str] = []
        self.openai_tasks: list[str] = []
        self.validator_tasks: list[str] = []
        self.finalized: bool = False

    def tool_handlers(self) -> dict[str, Callable[..., dict[str, str]]]:
        return {
            "set_research_goal": self.set_research_goal,
            "delegate_gemini_search": self.delegate_gemini_search,
            "delegate_openai_search": self.delegate_openai_search,
            "delegate_research_validation": self.delegate_research_validation,
            "finalize_orchestrator_plan": self.finalize_orchestrator_plan,
        }

    def set_research_goal(self, *, main_topic: str, required_outputs: list[str]) -> dict[str, str]:
        topic = main_topic.strip()
        outputs = [str(o).strip() for o in required_outputs if str(o).strip()]
        if not topic:
            return {"status": "error", "message": "main_topic must be non-empty."}
        if not outputs:
            return {"status": "error", "message": "required_outputs must have at least one item."}
        self.main_topic = topic
        self.required_outputs = outputs
        return {
            "status": "ok",
            "message": f"Research goal set: {topic!r} ({len(outputs)} outputs).",
        }

    def delegate_gemini_search(self, *, tasks: list[str]) -> dict[str, str]:
        cleaned = [t.strip() for t in tasks if t.strip()]
        if not cleaned:
            return {"status": "error", "message": "tasks must be a non-empty list."}
        self.gemini_tasks = cleaned
        return {"status": "ok", "message": f"Assigned {len(cleaned)} gemini_search subtasks."}

    def delegate_openai_search(self, *, tasks: list[str]) -> dict[str, str]:
        cleaned = [t.strip() for t in tasks if t.strip()]
        if not cleaned:
            return {"status": "error", "message": "tasks must be a non-empty list."}
        self.openai_tasks = cleaned
        return {"status": "ok", "message": f"Assigned {len(cleaned)} openai_search subtasks."}

    def delegate_research_validation(self, *, tasks: list[str]) -> dict[str, str]:
        cleaned = [t.strip() for t in tasks if t.strip()]
        if not cleaned:
            return {"status": "error", "message": "tasks must be a non-empty list."}
        self.validator_tasks = cleaned
        return {"status": "ok", "message": f"Assigned {len(cleaned)} validator focus areas."}

    def finalize_orchestrator_plan(self) -> dict[str, str]:
        missing: list[str] = []
        if not self.main_topic:
            missing.append("set_research_goal")
        if not self.gemini_tasks:
            missing.append("delegate_gemini_search")
        if not self.openai_tasks:
            missing.append("delegate_openai_search")
        if not self.validator_tasks:
            missing.append("delegate_research_validation")
        if missing:
            return {
                "status": "error",
                "message": f"Call these tools first: {', '.join(missing)}.",
            }
        self.finalized = True
        return {"status": "ok", "message": "Plan finalized. Ready to run search agents."}

    def is_complete(self) -> bool:
        return self.finalized

    def to_plan(self) -> OrchestratorPlan:
        if not self.finalized:
            raise ValueError("Orchestrator plan was not finalized via finalize_orchestrator_plan.")
        return OrchestratorPlan(
            orchestrator_config=OrchestratorConfig(),
            research_goal=ResearchGoal(
                main_topic=self.main_topic,
                required_outputs=self.required_outputs,
            ),
            execution_strategy=ExecutionStrategy(
                target_agents=[
                    TargetAgent(
                        agent_id="gemini_search",
                        model=self._settings.gemini_search_model,
                        tasks=self.gemini_tasks,
                    ),
                    TargetAgent(
                        agent_id="openai_search",
                        model=self._settings.openai_search_model,
                        tasks=self.openai_tasks,
                    ),
                    TargetAgent(
                        agent_id="research_validator",
                        model=self._settings.research_validator_model,
                        tasks=self.validator_tasks,
                    ),
                ],
            ),
        )

    @staticmethod
    def tool_result_json(payload: dict[str, str]) -> str:
        return json.dumps(payload, ensure_ascii=False)
