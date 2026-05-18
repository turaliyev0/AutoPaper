"""Shared helpers for research search agents."""

from __future__ import annotations

import json

from ...schemas import GatheredResearchBundle, GatheredTaskResult, OrchestratorPlan, SourceSnippet

RESEARCH_TASK_JSON_SYSTEM = """You are a research agent. Produce structured findings for one subtask.

Reply with JSON only:
{
  "summary": "<structured findings>",
  "key_points": ["point1", "point2"],
  "confidence": "high|medium|low",
  "limitations": "<uncertainty, cutoff, or missing data>"
}

No markdown fences."""


def task_user_payload(task: str, plan: OrchestratorPlan) -> str:
    return json.dumps(
        {
            "main_topic": plan.research_goal.main_topic,
            "required_outputs": plan.research_goal.required_outputs,
            "subtask": task,
        },
        indent=2,
    )


def result_from_json(
    *,
    task: str,
    agent_id: str,
    data: dict,
    sources: list[SourceSnippet] | None = None,
) -> GatheredTaskResult:
    return GatheredTaskResult(
        task=task,
        agent_id=agent_id,
        success=True,
        summary=str(data.get("summary") or ""),
        sources=sources or [],
        raw_notes=json.dumps(data, indent=2),
    )


def failed_result(*, task: str, agent_id: str, error: str) -> GatheredTaskResult:
    return GatheredTaskResult(task=task, agent_id=agent_id, success=False, error=error)
