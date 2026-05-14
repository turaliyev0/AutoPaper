from autopaper.validation.facts import FactConsistencyResult, llm_fact_pass_placeholder
from autopaper.validation.ieee_format import IEEEFormatHints
from autopaper.validation.plagiarism import PlagiarismReport, check_plagiarism

__all__ = [
    "FactConsistencyResult",
    "IEEEFormatHints",
    "PlagiarismReport",
    "check_plagiarism",
    "llm_fact_pass_placeholder",
]
