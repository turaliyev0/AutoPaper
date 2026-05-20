"""research.agents.search.base — grounding and confidence adjustment."""

from __future__ import annotations

import json

from research.agents.search import base as search_base
from research.agents.search.base import result_from_json, task_user_payload
from research.schemas import OrchestratorPlan, SourceSnippet


def test_has_citable_sources_doi_in_title() -> None:
    src = [
        SourceSnippet(
            url="#",
            title="Smith et al. (2020). A very long paper title here",
            excerpt="",
        ),
    ]
    assert search_base._has_citable_sources(src) is True


def test_has_citable_sources_empty() -> None:
    assert search_base._has_citable_sources([]) is False


def test_result_from_json_caps_high_confidence_without_sources() -> None:
    r = result_from_json(
        task="t",
        agent_id="gemini_search",
        data={
            "summary": "A short grounded summary.",
            "confidence": "high",
            "sources": [],
        },
    )
    assert r.success
    parsed = json.loads(r.raw_notes)
    assert parsed["confidence"] in ("medium", "low")


def test_result_from_json_textbook_tone_lowers_confidence() -> None:
    r = result_from_json(
        task="t",
        agent_id="openai_search",
        data={
            "summary": "It is well established that neural implants work forever.",
            "confidence": "high",
            "sources": [
                {
                    "title": "x",
                    "url": "#",
                },
            ],
        },
    )
    parsed = json.loads(r.raw_notes)
    assert parsed["confidence"] != "high"


def test_task_user_payload_includes_manuscript_when_present() -> None:
    plan = OrchestratorPlan.model_validate(
        {
            "orchestrator_config": {"agent_name": "SearchOrchestrator", "mode": "parallel_subtasking"},
            "research_goal": {"main_topic": "M", "required_outputs": ["a"]},
            "execution_strategy": {
                "action": "separate_into_subtopics",
                "target_agents": [
                    {"agent_id": "gemini_search", "model": "g", "tasks": ["t"]},
                    {"agent_id": "openai_search", "model": "o", "tasks": ["t"]},
                    {"agent_id": "research_validator", "model": "v", "tasks": ["v"]},
                ],
            },
        },
    )
    from research.manuscript_context import ManuscriptContext

    ctx = ManuscriptContext(summary="S", target_journal="J")
    raw = task_user_payload("sub", plan, manuscript=ctx)
    assert "M" in raw
    assert "manuscript" in raw
