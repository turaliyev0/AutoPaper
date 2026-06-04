"""Editor agents."""

from .orchestrator import EditorOrchestratorAgent
from .section_writer import SectionCoordinator, SectionWriterAgent
from .figure_agent import FigureAgent
from .manuscript_qa import ManuscriptQaAgent

__all__ = [
    "EditorOrchestratorAgent",
    "FigureAgent",
    "ManuscriptQaAgent",
    "SectionCoordinator",
    "SectionWriterAgent",
]
