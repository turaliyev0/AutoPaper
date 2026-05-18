"""Multi-Agent Research Pipeline (OpenAI + Gemini + Anthropic)."""

from .pipeline import ResearchPipeline
from .schemas import OrchestratorPlan, PipelineRunResult

__version__ = "1.0.0"
__all__ = ["OrchestratorPlan", "PipelineRunResult", "ResearchPipeline"]
