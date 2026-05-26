"""Shared helpers for research search agents."""

from __future__ import annotations

import json
import re
from typing import Any

from ...manuscript_context import ManuscriptContext
from ...schemas import GatheredTaskResult, OrchestratorPlan, SourceSnippet

# Unsupported essay tone when no citable sources back the claim.
_TEXTBOOK_PHRASES = (
    "the literature strongly supports",
    "prior research consistently demonstrates",
    "studies consistently demonstrate",
    "consistently demonstrate that",
    "studies have shown that",
    "it is well established that",
    "research overwhelmingly suggests",
    "numerous studies confirm",
)

_YEAR_IN_SOURCE = re.compile(r"\b(19|20)\d{2}\b")
_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def task_user_payload(
    task: str,
    plan: OrchestratorPlan,
    *,
    manuscript: ManuscriptContext | None = None,
) -> str:
    payload: dict[str, Any] = {
        "main_topic": plan.research_goal.main_topic,
        "required_outputs": plan.research_goal.required_outputs,
        "subtask": task,
    }
    if manuscript is not None:
        payload["manuscript"] = manuscript.to_search_dict()
    return json.dumps(payload, indent=2)


def _parse_sources(data: dict[str, Any]) -> list[SourceSnippet]:
    out: list[SourceSnippet] = []
    raw = data.get("sources")
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        excerpt = str(item.get("excerpt") or item.get("snippet") or "").strip()
        authors = str(item.get("authors") or "").strip()
        year = str(item.get("year") or "").strip()
        doi = str(item.get("doi") or "").strip()
        journal = str(item.get("journal") or "").strip()

        # Build a readable citation string: "Authors (Year). Title. Journal."
        if authors and year and title and authors not in title:
            title = f"{authors} ({year}). {title}"
        elif year and year not in title and title:
            title = f"{title} ({year})"
        if journal and journal not in title:
            title = f"{title}. {journal}"

        # DOIs from Gemini are frequently wrong — only embed if present (OpenAI search may supply them).
        if doi and doi not in title and doi not in excerpt:
            excerpt = f"DOI: {doi}. {excerpt}".strip()

        if title or url:
            out.append(SourceSnippet(url=url or "#", title=title or url, excerpt=excerpt))
    return out


def _has_citable_sources(sources: list[SourceSnippet]) -> bool:
    """At least one source looks like a real bibliographic entry (author + year + title).

    DOI presence is no longer required — Gemini outputs intentionally omit DOIs.
    A source with author-year in the title and a non-trivial title length is sufficient.
    """
    for src in sources:
        blob = f"{src.title} {src.excerpt} {src.url}"
        if _DOI_PATTERN.search(blob):
            return True
        if _YEAR_IN_SOURCE.search(blob) and len(src.title.strip()) >= 18:
            return True
        if " et al" in blob.lower() and _YEAR_IN_SOURCE.search(blob):
            return True
    return len(sources) >= 2 and all(len(s.title.strip()) >= 20 for s in sources)


def _normalize_summary_text(summary: Any) -> str:
    if isinstance(summary, list):
        return " ".join(str(item) for item in summary)
    return str(summary or "")


def _summary_has_textbook_tone(summary: Any) -> bool:
    low = _normalize_summary_text(summary).lower()
    return any(phrase in low for phrase in _TEXTBOOK_PHRASES)


def _adjust_confidence(data: dict[str, Any], sources: list[SourceSnippet]) -> dict[str, Any]:
    """Model-only search: cap confidence when claims lack citable sources or essay tone."""
    data = dict(data)
    conf = str(data.get("confidence") or "medium").lower()
    lim_parts: list[str] = []

    citable = _has_citable_sources(sources)
    summary = _normalize_summary_text(data.get("summary"))

    if not sources:
        if conf == "high":
            conf = "medium"
        lim_parts.append("No bibliographic sources listed (model knowledge only).")
    elif not citable:
        if conf == "high":
            conf = "medium"
        lim_parts.append(
            "Sources lack verifiable bibliographic detail (year, DOI, or author–year); "
            "treat as illustrative only.",
        )

    if _summary_has_textbook_tone(summary):
        if conf == "high":
            conf = "medium"
        if conf == "medium" and not citable:
            conf = "low"
        lim_parts.append(
            "Summary used unsupported generalization language; prefer named citations in sources.",
        )

    if conf == "high" and not citable:
        conf = "medium"

    data["confidence"] = conf
    if lim_parts:
        existing = str(data.get("limitations") or "").strip()
        extra = " ".join(lim_parts)
        data["limitations"] = f"{existing} {extra}".strip() if existing else extra
    return data


def result_from_json(
    *,
    task: str,
    agent_id: str,
    data: dict,
    sources: list[SourceSnippet] | None = None,
) -> GatheredTaskResult:
    parsed_sources = sources if sources is not None else _parse_sources(data)
    data = _adjust_confidence(data, parsed_sources)
    summary = _normalize_summary_text(data.get("summary"))
    return GatheredTaskResult(
        task=task,
        agent_id=agent_id,
        success=True,
        summary=summary,
        sources=parsed_sources,
        raw_notes=json.dumps(data, indent=2, ensure_ascii=False),
    )


def failed_result(*, task: str, agent_id: str, error: str) -> GatheredTaskResult:
    return GatheredTaskResult(task=task, agent_id=agent_id, success=False, error=error)
