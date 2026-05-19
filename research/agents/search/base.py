"""Shared helpers for research search agents."""

from __future__ import annotations

import json
from typing import Any

from ...manuscript_context import ManuscriptContext
from ...schemas import GatheredTaskResult, OrchestratorPlan, SourceSnippet


def task_user_payload(
    task: str,
    plan: OrchestratorPlan,
    *,
    manuscript: ManuscriptContext | None = None,
) -> str:
    payload: dict[str, Any] = {
        "main_topic": plan.research_goal.main_topic,
        "required_outputs": plan.research_goal.required_outputs,
        "subtask": task,
    }
    if manuscript is not None:
        payload["manuscript"] = manuscript.to_search_dict()
    return json.dumps(payload, indent=2)


def _parse_sources(data: dict[str, Any]) -> list[SourceSnippet]:
    out: list[SourceSnippet] = []
    raw = data.get("sources")
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        excerpt = str(item.get("excerpt") or item.get("snippet") or "").strip()
        if title or url:
            out.append(SourceSnippet(url=url or "#", title=title or url, excerpt=excerpt))
    return out


def _adjust_confidence(data: dict[str, Any], sources: list[SourceSnippet]) -> dict[str, Any]:
    """Model-only search: cap confidence when no citable sources were provided."""
    if sources:
        return data
    conf = str(data.get("confidence") or "medium").lower()
    if conf == "high":
        data = dict(data)
        data["confidence"] = "medium"
        lim = str(data.get("limitations") or "").strip()
        note = "No bibliographic sources listed (model knowledge only)."
        data["limitations"] = f"{lim} {note}".strip() if lim else note
    return data


def result_from_json(
    *,
    task: str,
    agent_id: str,
    data: dict,
    sources: list[SourceSnippet] | None = None,
) -> GatheredTaskResult:
    parsed_sources = sources if sources is not None else _parse_sources(data)
    data = _adjust_confidence(data, parsed_sources)
    return GatheredTaskResult(
        task=task,
        agent_id=agent_id,
        success=True,
        summary=str(data.get("summary") or ""),
        sources=parsed_sources,
        raw_notes=json.dumps(data, indent=2, ensure_ascii=False),
    )


def failed_result(*, task: str, agent_id: str, error: str) -> GatheredTaskResult:
    return GatheredTaskResult(task=task, agent_id=agent_id, success=False, error=error)
