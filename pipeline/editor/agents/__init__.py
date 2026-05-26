"""Editor agents."""

from .orchestrator import EditorOrchestratorAgent
from .section_writer import SectionCoordinator, SectionWriterAgent
from .ieee_validator import IeeeValidatorAgent
from .figure_agent import FigureAgent

__all__ = [
    "EditorOrchestratorAgent",
    "FigureAgent",
    "IeeeValidatorAgent",
    "SectionCoordinator",
    "SectionWriterAgent",
]
