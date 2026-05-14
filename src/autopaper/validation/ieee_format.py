from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class IEEEFormatHints:
    """Lightweight heuristics; replace with template-aware validator later."""

    issues: list[str]

    @classmethod
    def scan(cls, text: str) -> "IEEEFormatHints":
        issues: list[str] = []
        if len(text.split()) > 250 and "\\begin{abstract}" not in text and "Abstract" not in text[:800]:
            issues.append("Abstract heading or LaTeX abstract environment not obvious in excerpt.")
        if not re.search(r"\b(Fig\.|Figure|Table|Eq\.|Equation)\b", text, re.I):
            issues.append("No obvious cross-references to figures, tables, or equations.")
        return cls(issues=issues)
