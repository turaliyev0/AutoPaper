"""Pydantic v2 models for orchestrator JSON and inter-agent payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .config import ACTIVE_SEARCH_AGENT_IDS

# All known search agent ids (legacy plans may still reference disabled agents).
SEARCH_AGENT_IDS = frozenset(
    {"gemini_search", "openai_search", "claude_search", "exa_search"},
)
REPORT_SYNTHESIZER_ID = "report_synthesizer"
_LEGACY_SYNTHESIZER_IDS = frozenset({"claude_analyst", REPORT_SYNTHESIZER_ID})


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
        has_synth = bool(ids & _LEGACY_SYNTHESIZER_IDS)
        if not has_search:
            raise ValueError(
                "execution_strategy must include at least one active search agent: "
                "gemini_search, openai_search"
            )
        if not has_synth:
            raise ValueError(
                "execution_strategy must include report_synthesizer (or legacy claude_analyst)"
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

    def synthesizer_agent(self) -> TargetAgent | None:
        return self.agent_by_id(REPORT_SYNTHESIZER_ID) or self.agent_by_id("claude_analyst")


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


class PipelineRunResult(BaseModel):
    plan: OrchestratorPlan
    bundle: GatheredResearchBundle | None = None
    report: SynthesisReport | None = None
    output_dir: str = ""
    errors: list[str] = Field(default_factory=list)
