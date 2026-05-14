from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FactConsistencyResult:
    flags: list[str]


async def llm_fact_pass_placeholder(flags: list[str]) -> FactConsistencyResult:
    """Wire to a dedicated verifier model or symbolic checks."""
    return FactConsistencyResult(flags=flags or ["No automated fact engine configured."])
