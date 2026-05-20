"""Tests for per-task research artifact paths."""

from __future__ import annotations

from pathlib import Path

from research.research_storage import task_artifact_slug, write_research_bundle
from research.schemas import GatheredResearchBundle, GatheredTaskResult, OrchestratorPlan


def _minimal_plan() -> OrchestratorPlan:
    raw = {
        "orchestrator_config": {"agent_name": "SearchOrchestrator", "mode": "parallel_subtasking"},
        "research_goal": {"main_topic": "t", "required_outputs": ["a"]},
        "execution_strategy": {
            "action": "separate_into_subtopics",
            "target_agents": [
                {"agent_id": "gemini_search", "model": "g", "tasks": ["task one"]},
                {"agent_id": "openai_search", "model": "o", "tasks": ["task two"]},
                {"agent_id": "research_validator", "model": "v", "tasks": ["validate sources"]},
            ],
        },
    }
    return OrchestratorPlan.model_validate(raw)


def test_task_slug_stable() -> None:
    a = task_artifact_slug("gemini_search", 1, "Compare SNR metrics")
    b = task_artifact_slug("gemini_search", 1, "Compare SNR metrics")
    assert a == b
    assert a.startswith("01_gemini_search_")


def test_write_research_bundle_creates_files(tmp_path: Path) -> None:
    plan = _minimal_plan()
    bundle = GatheredResearchBundle(
        plan=plan,
        results=[
            GatheredTaskResult(
                task="task one",
                agent_id="gemini_search",
                success=True,
                summary="finding",
            ),
        ],
    )
    research_dir = write_research_bundle(
        tmp_path,
        bundle,
        research_dir_name="06_research",
        aggregate_filename="06_gathered_research.json",
    )
    assert research_dir.is_dir()
    assert (research_dir / "manifest.json").is_file()
    json_files = list(research_dir.glob("*.json"))
    assert len(json_files) >= 2  # manifest + at least one task
    assert (tmp_path / "06_gathered_research.json").is_file()
