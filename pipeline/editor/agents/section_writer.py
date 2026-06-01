"""Section writer agent — writes one IEEE section as LaTeX body text."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pipeline.research.clients.gemini_client import GeminiClient
from pipeline.research.utils import extract_json_object

from pipeline.research.task_kinds import RESULTS_FORBIDDEN_KINDS

from ..assembler import _normalize_body_paragraphs
from ..context import EditorContext
from ..section_prose import sanitize_section_latex
from ..prompts.loader import load_section_writer_instruction
from ..schemas import (
    CitationEntry,
    EditorPlan,
    EditorValidationResult,
    SectionDraft,
    SectionSpec,
)

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
        if not artifact or not artifact.is_trusted:
            continue
        if spec.section_id == "results" and artifact.task_kind in RESULTS_FORBIDDEN_KINDS:
            continue
        entry: dict[str, str] = {
            "slug": slug,
            "task": artifact.task[:120],
            "summary": artifact.short_summary(1200),
            "task_kind": artifact.task_kind,
            "data_provenance": artifact.data_provenance,
        }
        if artifact.data_provenance == "literature_only":
            entry["usage_rule"] = (
                "LITERATURE ONLY — cite with \\cite{{}}; never present as this study's data."
            )
        research_summaries.append(entry)

    # --- collect manuscript content for mapped parts ---
    manuscript_content: dict[str, Any] = {}
    source_path_filters: list[str] = []
    for part in spec.manuscript_parts:
        if part == "summary":
            manuscript_content["summary"] = context.manuscript.summary[:1000]
        elif part == "key_claims":
            manuscript_content["key_claims"] = context.manuscript.key_claims[:16]
        elif part == "experimental_design":
            manuscript_content["experimental_design"] = context.manuscript.experimental_design_bullets()
        elif part == "methods_text":
            manuscript_content["methods_text"] = context.manuscript.get_text_block("method")[:1200]
        elif part == "mismatch_flags":
            manuscript_content["mismatch_flags"] = [
                {"image": f.get("image_path"), "issue": f.get("issue")}
                for f in context.manuscript.mismatch_flags
            ]
        elif part == "source_text_blocks":
            manuscript_content["source_text_blocks"] = context.manuscript.primary_source()
        elif part.startswith("source_text:"):
            frag = part.split(":", 1)[1].strip()
            if frag:
                source_path_filters.append(frag)
                manuscript_content[f"source_text_{frag.replace('/', '_')}"] = (
                    context.manuscript.primary_source(path_filter=frag)
                )

    # Always pass full 04 source; optional filters add section-focused slices
    primary_manuscript_source = context.manuscript.primary_source()
    if source_path_filters:
        primary_manuscript_source["section_focus_paths"] = source_path_filters
        primary_manuscript_source["section_focus_blocks"] = [
            context.manuscript.primary_source(path_filter=frag)
            for frag in source_path_filters
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

    measured = context.manuscript.has_measured_outcomes()
    outcome_lines = context.manuscript.quantitative_outcome_lines()
    duration_weeks = context.manuscript.study_duration_weeks()

    payload: dict[str, Any] = {
        "section_id": spec.section_id,
        "heading": spec.heading,
        "ieee_format": context.ieee_format,
        "notes": spec.notes,
        "primary_manuscript_source": primary_manuscript_source,
        "manuscript_content": manuscript_content,
        "research_summaries": research_summaries,
        "citation_pool": citation_pool,
        "article_title": context.title,
        "available_figure_ids": spec.available_figure_ids,
        "has_measured_outcomes": measured,
        "quantitative_evidence": outcome_lines,
        "study_duration_weeks": duration_weeks,
    }
    if measured:
        payload["writing_requirement"] = (
            "Reported outcomes exist in quantitative_evidence. "
            "Abstract, Results, Discussion, and Conclusion must cite at least "
            "three distinct numeric values from that list (with units). "
            "Do not replace them with vague qualitative-only claims."
        )
    else:
        payload["writing_requirement"] = (
            "No measured outcome table is in the manuscript source. "
            "Do not invent impedance, SNR, histology, or p-values. "
            "State objectives and methods in past tense; frame outcomes as "
            "anticipated or under evaluation — not as completed findings. "
            "Never mention missing protocol fields, 'not provided', or the pipeline."
        )
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

    def __init__(self, client: GeminiClient) -> None:
        self._client = client
        self._system = load_section_writer_instruction()

    async def write_section(
        self,
        spec: SectionSpec,
        context: EditorContext,
    ) -> SectionDraft:
        return await self._generate(spec, context, revision=None)

    async def rewrite_section(
        self,
        spec: SectionSpec,
        context: EditorContext,
        *,
        prior: SectionDraft,
        validation: EditorValidationResult,
    ) -> SectionDraft:
        revision = {
            "mode": "ieee_validator_revision",
            "validation_score": validation.score,
            "validation_verdict": validation.verdict,
            "issues_to_fix": validation.issues,
            "validator_notes": validation.notes,
            "previous_latex_body": prior.latex_body[:8000],
            "instruction": (
                "Rewrite this section to fix every listed validation issue. "
                "Use IEEE numeric \\cite{key} only from citation_pool. "
                "Use Fig.~\\ref{fig:ID} for figures — never hardcoded numbers or raw image paths. "
                "Remove any pipeline/internal tool terms. Report original study data in Results only."
            ),
        }
        return await self._generate(spec, context, revision=revision)

    async def _generate(
        self,
        spec: SectionSpec,
        context: EditorContext,
        *,
        revision: dict[str, Any] | None,
    ) -> SectionDraft:
        known_citekeys = frozenset(c.citekey for c in context.citation_pool)
        payload = json.loads(_build_section_payload(spec, context))
        if revision:
            payload["revision"] = revision
        user = json.dumps(payload, indent=2, ensure_ascii=False)
        label = (
            f"section_writer:rewrite:{spec.section_id}"
            if revision
            else f"section_writer:{spec.section_id}"
        )
        try:
            data = await self._client.generate_json(
                system=self._system,
                user=user,
                trace_label=label,
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


def _strip_unknown_cites(latex_body: str, known_citekeys: frozenset[str]) -> str:
    """Remove \\cite{...} entries whose keys are not in the bibliography pool."""

    def _repl(match: re.Match[str]) -> str:
        keys = [k.strip() for k in match.group(1).split(",") if k.strip()]
        valid = [k for k in keys if k in known_citekeys]
        if not valid:
            return ""
        return f"\\cite{{{', '.join(valid)}}}"

    text = re.sub(r"\\cite\{([^}]+)\}", _repl, latex_body)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"  +", " ", text)
    return text


def _draft_from_json(
    spec: SectionSpec,
    data: dict[str, Any],
    known_citekeys: frozenset[str] | None = None,
) -> SectionDraft:
    latex_body = _normalize_body_paragraphs(
        _normalize_backslashes(str(data.get("latex_body") or ""))
    )

    latex_body = sanitize_section_latex(
        _strip_unknown_cites(latex_body, known_citekeys or frozenset())
    )

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

    @staticmethod
    def _figures_for_section(spec: SectionSpec, plan: EditorPlan) -> list[dict[str, str]]:
        """Figures this section may introduce — only explicit primary_sections matches."""
        return [
            {"figure_id": f.figure_id, "caption": f.caption[:80]}
            for f in plan.figures
            if spec.section_id in f.primary_sections
        ]

    async def write_all(
        self,
        plan: EditorPlan,
        context: EditorContext,
    ) -> list[SectionDraft]:
        for spec in plan.sections:
            spec.available_figure_ids = self._figures_for_section(spec, plan)

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
