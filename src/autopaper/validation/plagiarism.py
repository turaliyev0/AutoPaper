from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PlagiarismReport:
    """Placeholder for an external or local plagiarism engine."""

    score: float | None = None
    notes: str = ""

    async def analyze(self, text: str) -> "PlagiarismReport":
        return PlagiarismReport(score=None, notes="Not implemented; integrate engine here.")


async def check_plagiarism(text: str) -> PlagiarismReport:
    return await PlagiarismReport().analyze(text)
