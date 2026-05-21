"""Section writer agent — writes one IEEE section as LaTeX body text."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from research.clients.openai_client import OpenAIClient
from research.utils import extract_json_object

from ..context import EditorContext
from ..prompts.loader import load_section_writer_instruction
from ..schemas import CitationEntry, EditorPlan, SectionDraft, SectionSpec

logger = logging.getLogger(__name__)

AGENT_ID = "section_writer"


def _build_section_payload(
    spec: SectionSpec,
    context: EditorContext,
) -> str:
    """Build the user JSON payload for one section writing task."""
    # --- collect research summaries for mapped slugs ---
    research_summaries: list[dict[str, str]] = []
    for slug in spec.research_slugs:
        artifact = context.artifact_by_slug(slug)
        if artifact and artifact.is_trusted:
            research_summaries.append({
                "slug": slug,
                "task": artifact.task[:120],
                "summary": artifact.short_summary(600),
            })

    # --- collect manuscript content for mapped parts ---
    manuscript_content: dict[str, Any] = {}
    for part in spec.manuscript_parts:
        if part == "summary":
            manuscript_content["summary"] = context.manuscript.summary[:1000]
        elif part == "key_claims":
            manuscript_content["key_claims"] = context.manuscript.key_claims[:10]
        elif part == "experimental_design":
            manuscript_content["experimental_design"] = context.manuscript.experimental_design_bullets()
        elif part == "methods_text":
            manuscript_content["methods_text"] = context.manuscript.get_text_block("method")[:1200]
        elif part == "mismatch_flags":
            manuscript_content["mismatch_flags"] = [
                {"image": f.get("image_path"), "issue": f.get("issue")}
                for f in context.manuscript.mismatch_flags
            ]

    # --- citation pool (abbreviated) ---
    citation_pool = [
        {
            "citekey": c.citekey,
            "authors": c.authors,
            "year": c.year,
            "title": c.title[:80],
            "journal": c.journal,
        }
        for c in context.citation_pool[:30]
    ]

    payload: dict[str, Any] = {
        "section_id": spec.section_id,
        "heading": spec.heading,
        "ieee_format": context.ieee_format,
        "max_words": spec.max_words,
        "notes": spec.notes,
        "manuscript_content": manuscript_content,
        "research_summaries": research_summaries,
        "citation_pool": citation_pool,
        "article_title": context.title,
        "available_figure_ids": spec.available_figure_ids,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _count_words(latex: str) -> int:
    """Approximate word count: strip LaTeX commands, count words."""
    text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", latex)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"[{}%]", " ", text)
    return len(text.split())


def _normalize_backslashes(latex: str) -> str:
    """
    Fix LLM double-escaping: ``\\\\cite`` → ``\\cite`` (and all other commands).

    When an LLM returns LaTeX inside a JSON string it sometimes double-escapes
    backslashes, producing ``\\command`` (two backslashes) instead of ``\\command``
    (one backslash). This corrects ``\\<letter>`` → ``\\<letter>`` while
    preserving legitimate ``\\\\`` (LaTeX line-break) which is NOT followed
    directly by a letter.
    """
    return re.sub(r"\\\\([a-zA-Z])", r"\\\1", latex)


class SectionWriterAgent:
    """Writes one IEEE section as a LaTeX body fragment."""

    def __init__(self, client: OpenAIClient) -> None:
        self._client = client
        self._system = load_section_writer_instruction()

    async def write_section(
        self,
        spec: SectionSpec,
        context: EditorContext,
    ) -> SectionDraft:
        known_citekeys = frozenset(c.citekey for c in context.citation_pool)
        user = _build_section_payload(spec, context)
        try:
            data = await self._client.generate_json(
                system=self._system,
                user=user,
                trace_label=f"section_writer:{spec.section_id}",
            )
            return _draft_from_json(spec, data, known_citekeys=known_citekeys)
        except Exception as exc:
            logger.exception("SectionWriter failed for %s: %s", spec.section_id, exc)
            return SectionDraft(
                section_id=spec.section_id,
                heading=spec.heading,
                success=False,
                error=str(exc),
                agent_id=AGENT_ID,
            )


def _draft_from_json(
    spec: SectionSpec,
    data: dict[str, Any],
    known_citekeys: frozenset[str] | None = None,
) -> SectionDraft:
    latex_body = _normalize_backslashes(str(data.get("latex_body") or ""))

    # Sync figures_referenced with refs actually present in the body
    # so the validator never sees a mismatch between declaration and usage.
    raw_figs = [str(f) for f in (data.get("figures_referenced") or []) if isinstance(f, str)]
    body_fig_ids = set(re.findall(r"\\ref\{fig:([^}]+)\}", latex_body))
    figures_referenced = [f for f in raw_figs if f in body_fig_ids]
    # Also add any refs found in body that weren't declared (defensive)
    for fid in body_fig_ids:
        if fid not in figures_referenced:
            figures_referenced.append(fid)

    # Abstract / index terms must not trigger duplicate figure floats in the PDF
    if spec.section_id in ("abstract", "index_terms"):
        figures_referenced = []

    # Filter citations to known keys only — prevents hallucinated citekeys from failing validation
    raw_cites = [str(c) for c in (data.get("citations_used") or []) if isinstance(c, str)]
    if known_citekeys is not None:
        citations_used = [c for c in raw_cites if c in known_citekeys]
    else:
        citations_used = raw_cites

    return SectionDraft(
        section_id=spec.section_id,
        heading=spec.heading,
        latex_body=latex_body,
        citations_used=citations_used,
        figures_referenced=figures_referenced,
        word_count=_count_words(latex_body),
        agent_id=AGENT_ID,
        success=bool(latex_body.strip()),
        error=None if latex_body.strip() else "Empty latex_body returned.",
    )


class SectionCoordinator:
    """Runs all section writing tasks in parallel (mirrors SearchCoordinator)."""

    def __init__(self, writer: SectionWriterAgent) -> None:
        self._writer = writer

    async def write_all(
        self,
        plan: EditorPlan,
        context: EditorContext,
    ) -> list[SectionDraft]:
        # Inject figure IDs so every section writer knows valid cross-reference IDs
        fig_index = [
            {"figure_id": f.figure_id, "caption": f.caption[:80]}
            for f in plan.figures
        ]
        for spec in plan.sections:
            spec.available_figure_ids = fig_index

        # Stagger launches slightly to reduce simultaneous API bursts
        import asyncio as _asyncio

        async def _delayed(spec: "SectionSpec", delay: float) -> "SectionDraft":
            if delay > 0:
                await _asyncio.sleep(delay)
            return await self._writer.write_section(spec, context)

        coros = [
            _delayed(spec, i * 1.5)
            for i, spec in enumerate(plan.ordered_sections)
        ]
        if not coros:
            raise ValueError("Editor plan has no sections. Call map_section_sources first.")
        logger.info("SectionCoordinator: writing %d sections in parallel", len(coros))
        results = await asyncio.gather(*coros, return_exceptions=True)

        drafts: list[SectionDraft] = []
        for spec, item in zip(plan.ordered_sections, results):
            if isinstance(item, BaseException):
                logger.exception("Section %s crashed: %s", spec.section_id, item)
                drafts.append(SectionDraft(
                    section_id=spec.section_id,
                    heading=spec.heading,
                    success=False,
                    error=str(item),
                    agent_id=AGENT_ID,
                ))
            else:
                drafts.append(item)

        ok = sum(1 for d in drafts if d.success)
        logger.info("SectionCoordinator: %d/%d sections succeeded", ok, len(drafts))
        return drafts
