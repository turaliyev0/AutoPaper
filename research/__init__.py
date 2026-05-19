"""Multi-Agent Research Pipeline (OpenAI orchestrator + Gemini/OpenAI search)."""

from .pipeline import ResearchPipeline
from .schemas import OrchestratorPlan, PipelineRunResult

__version__ = "1.2.0"
__all__ = ["OrchestratorPlan", "PipelineRunResult", "ResearchPipeline"]
