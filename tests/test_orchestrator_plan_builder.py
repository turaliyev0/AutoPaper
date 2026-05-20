"""OrchestratorPlanBuilder: tool handlers and finalize/to_plan (no network)."""

from __future__ import annotations

import pytest

from research.agents.orchestrator_tools import OrchestratorPlanBuilder
from research.config import Settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-unit-tests")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    return Settings(_env_file=None)


def test_finalize_fails_without_prior_steps(settings: Settings) -> None:
    b = OrchestratorPlanBuilder(settings)
    out = b.finalize_orchestrator_plan()
    assert out["status"] == "error"
    assert "set_research_goal" in out["message"]


def test_delegate_gemini_empty_tasks_error(settings: Settings) -> None:
    b = OrchestratorPlanBuilder(settings)
    assert b.delegate_gemini_search(tasks=[])["status"] == "error"


def test_happy_path_builds_valid_plan(settings: Settings) -> None:
    b = OrchestratorPlanBuilder(settings)
    assert b.set_research_goal(main_topic="Topic X", required_outputs=["Out A", "Out B"])[
        "status"
    ] == "ok"
    assert b.delegate_gemini_search(tasks=["g1", "g2"])["status"] == "ok"
    assert b.delegate_openai_search(tasks=["o1"])["status"] == "ok"
    assert b.delegate_research_validation(tasks=["validate sources"])["status"] == "ok"
    fin = b.finalize_orchestrator_plan()
    assert fin["status"] == "ok"
    assert b.is_complete()

    plan = b.to_plan()
    assert plan.research_goal.main_topic == "Topic X"
    assert plan.research_goal.required_outputs == ["Out A", "Out B"]
    ids = [a.agent_id for a in plan.execution_strategy.target_agents]
    assert ids == ["gemini_search", "openai_search", "research_validator"]
    assert [len(a.tasks) for a in plan.execution_strategy.target_agents] == [2, 1, 1]


def test_finalize_fails_if_validator_missing(settings: Settings) -> None:
    b = OrchestratorPlanBuilder(settings)
    b.set_research_goal(main_topic="T", required_outputs=["a"])
    b.delegate_gemini_search(tasks=["g"])
    b.delegate_openai_search(tasks=["o"])
    out = b.finalize_orchestrator_plan()
    assert out["status"] == "error"
    assert "delegate_research_validation" in out["message"]
