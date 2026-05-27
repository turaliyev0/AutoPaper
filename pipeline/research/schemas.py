"""Pydantic v2 models for orchestrator JSON and inter-agent payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .config import ACTIVE_SEARCH_AGENT_IDS

RESEARCH_VALIDATOR_ID = "research_validator"
_VALIDATOR_IDS = frozenset({RESEARCH_VALIDATOR_ID})


class OrchestratorConfig(BaseModel):
    agent_name: str = "SearchOrchestrator"
    mode: Literal["parallel_subtasking", "sequential"] = "parallel_subtasking"
    allow_cross_model_validation: bool = True


class ResearchGoal(BaseModel):
    main_topic: str
    required_outputs: list[str] = Field(min_length=1)


class TargetAgent(BaseModel):
    agent_id: str
    model: str
    tasks: list[str] = Field(min_length=1)


class ExecutionStrategy(BaseModel):
    action: Literal["separate_into_subtopics"] = "separate_into_subtopics"
    target_agents: list[TargetAgent] = Field(min_length=1)

    @field_validator("target_agents")
    @classmethod
    def must_include_search_and_synthesis(cls, agents: list[TargetAgent]) -> list[TargetAgent]:
        ids = {a.agent_id for a in agents}
        has_search = bool(ids & ACTIVE_SEARCH_AGENT_IDS) or "gemini_explorer" in ids
        has_validator = bool(ids & _VALIDATOR_IDS)
        if not has_search:
            raise ValueError(
                "execution_strategy must include at least one active search agent: "
                "gemini_search, openai_search"
            )
        if not has_validator:
            raise ValueError(
                "execution_strategy must include research_validator"
            )
        return agents


class OrchestratorPlan(BaseModel):
    """Exact top-level schema the Orchestrator must produce."""

    orchestrator_config: OrchestratorConfig
    research_goal: ResearchGoal
    execution_strategy: ExecutionStrategy

    def agent_by_id(self, agent_id: str) -> TargetAgent | None:
        for agent in self.execution_strategy.target_agents:
            if agent.agent_id == agent_id:
                return agent
        return None

    def validator_agent(self) -> TargetAgent | None:
        return self.agent_by_id(RESEARCH_VALIDATOR_ID)


class SourceSnippet(BaseModel):
    url: str
    title: str = ""
    excerpt: str = ""


class GatheredTaskResult(BaseModel):
    task: str
    agent_id: str
    success: bool
    summary: str = ""
    sources: list[SourceSnippet] = Field(default_factory=list)
    raw_notes: str = ""
    error: str | None = None


class GatheredResearchBundle(BaseModel):
    plan: OrchestratorPlan
    results: list[GatheredTaskResult] = Field(default_factory=list)
    completed_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def successful_results(self) -> list[GatheredTaskResult]:
        return [r for r in self.results if r.success]

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "research_goal": self.plan.research_goal.model_dump(),
            "gathered_findings": [r.model_dump() for r in self.results],
        }


class SynthesisReport(BaseModel):
    title: str
    markdown_body: str
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ValidatedTaskResult(BaseModel):
    """Validator output for one search task artifact."""

    slug: str
    research_filename: str
    agent_id: str
    task: str
    verdict: Literal["pass", "warn", "fail"]
    source_quality: Literal["clear", "weak", "missing"] = "missing"
    clarity: Literal["clear", "unclear", "contradictory"] = "unclear"
    coverage: Literal["sufficient", "partial", "insufficient"] = "partial"
    gaps: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    source_notes: str = ""
    task_kind: str = "unknown"
    data_provenance: Literal[
        "literature_only",
        "manuscript_only",
        "mixed",
        "unknown",
    ] = "unknown"
    overview: str = Field(
        default="",
        description=(
            "5–10 sentence neutral overview of what this research task found, "
            "for downstream editor orchestrator slug assignment."
        ),
    )
    validated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ValidatedResearchBundle(BaseModel):
    plan: OrchestratorPlan
    results: list[ValidatedTaskResult] = Field(default_factory=list)
    completed_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class PipelineRunResult(BaseModel):
    plan: OrchestratorPlan
    bundle: GatheredResearchBundle | None = None
    validated: ValidatedResearchBundle | None = None
    report: SynthesisReport | None = None
    output_dir: str = ""
    errors: list[str] = Field(default_factory=list)
