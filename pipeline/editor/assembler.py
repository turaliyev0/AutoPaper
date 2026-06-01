"""Assembles SectionDrafts + figures into a complete IEEEtran LaTeX document."""

from __future__ import annotations

import re
from pathlib import Path

from .context import EditorContext
from .schemas import CitationEntry, EditorPlan, FigureResult, SectionDraft

# ---------------------------------------------------------------------------
# IEEEtran preamble
# ---------------------------------------------------------------------------

_CONFERENCE_CLASS = r"\documentclass[conference]{IEEEtran}"
_JOURNAL_CLASS = r"\documentclass[journal]{IEEEtran}"

_PREAMBLE_PACKAGES = r"""\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{cite}
\usepackage{url}
\usepackage{hyperref}"""


def _preamble(
    title: str,
    authors: list[dict],
    ieee_format: str,
) -> str:
    doc_class = _CONFERENCE_CLASS if ieee_format == "conference" else _JOURNAL_CLASS
    author_block = _build_author_block(authors, ieee_format)
    return (
        f"{doc_class}\n"
        f"{_PREAMBLE_PACKAGES}\n\n"
        r"\begin{document}" + "\n\n"
        f"\\title{{{_escape_latex(title)}}}\n\n"
        f"{author_block}\n\n"
        r"\maketitle" + "\n"
    )


def _build_author_block(authors: list[dict], ieee_format: str) -> str:
    if not authors:
        return r"\author{\IEEEauthorblockN{Author Name}\IEEEauthorblockA{Institution}}"
    parts: list[str] = []
    for a in authors[:6]:
        name = _escape_latex(str(a.get("name") or ""))
        affil = _escape_latex(str(a.get("affiliation") or ""))
        parts.append(
            f"\\IEEEauthorblockN{{{name}}}\n"
            f"\\IEEEauthorblockA{{{affil}}}"
        )
    joined = "\n\\and\n".join(parts)
    return f"\\author{{\n{joined}\n}}"


def _escape_latex(text: str) -> str:
    for char, repl in (
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
        ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
        ("^", r"\^{}"),
    ):
        text = text.replace(char, repl)
    return text


def _normalize_body_paragraphs(body: str) -> str:
    """
    Convert JSON-escaped newlines (``\\n\\n`` literals) to real LaTeX paragraph breaks.
    """
    text = body.replace("\\n\\n", "\n\n").replace("\\n", "\n")
    # Collapse runs of 3+ newlines to a standard paragraph break
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ieee_index_terms(terms: str) -> str:
    """Sentence-style index terms (IEEE): lowercase generic phrases; keep acronyms in parens."""
    parts = [p.strip() for p in terms.split(",") if p.strip()]
    normalized: list[str] = []
    for part in parts:
        if part.isupper() or "(" in part:
            normalized.append(part)
            continue
        if part == part.title() and len(part.split()) > 1:
            normalized.append(part.lower())
        else:
            normalized.append(part)
    return ", ".join(normalized)


# ---------------------------------------------------------------------------
# Section rendering
# ---------------------------------------------------------------------------


def _render_section(draft: SectionDraft, order: int) -> str:
    """Convert a SectionDraft to LaTeX. Abstract / Index Terms get special treatment."""
    sid = draft.section_id.lower()
    heading = draft.heading
    body = _normalize_body_paragraphs(draft.latex_body or "")

    if sid == "abstract":
        return f"\\begin{{abstract}}\n{body}\n\\end{{abstract}}\n"

    if sid == "index_terms":
        # IEEEkeywords environment
        terms = re.sub(r"^index terms?\s*[:\-—]?\s*", "", body, flags=re.IGNORECASE)
        terms = _ieee_index_terms(terms)
        return f"\\begin{{IEEEkeywords}}\n{terms}\n\\end{{IEEEkeywords}}\n"

    if sid == "references":
        return ""  # handled by bibliography

    clean_heading = _strip_section_numbering(heading)
    return (
        f"\\section{{{_escape_latex(clean_heading)}}}\n"
        f"\\label{{sec:{draft.section_id}}}\n\n"
        f"{body}\n"
    )


def _to_roman(n: int) -> str:
    vals = [10, 9, 5, 4, 1]
    syms = ["X", "IX", "V", "IV", "I"]
    result = ""
    for v, s in zip(vals, syms):
        while n >= v:
            result += s
            n -= v
    return result


def _strip_section_numbering(heading: str) -> str:
    """
    Remove any leading section numbering the orchestrator may have added.
    IEEEtran auto-numbers sections, so 'I. Introduction' must become 'Introduction'.
    Handles: 'I. Foo', 'II. Foo', 'III. Foo', '1. Foo', '1.1 Foo', 'A. Foo'.
    """
    return re.sub(r"^(?:[IVXLC]+\.|[A-Z]\.|[\d]+(?:\.\d+)*\.?)\s+", "", heading).strip()


# ---------------------------------------------------------------------------
# Figure inclusion
# ---------------------------------------------------------------------------


def _render_figure(fig: FigureResult, spec_caption: str, fig_num: int) -> str:
    if not fig.success or not fig.output_path:
        return (
            f"% Figure {fig.figure_id} failed to generate. "
            f"Error: {fig.error or 'unknown'}\n"
        )
    # Use relative path from manuscript dir
    rel_path = Path(fig.output_path).name
    return (
        f"\\begin{{figure}}[htbp]\n"
        f"  \\centering\n"
        f"  \\includegraphics[width=\\linewidth]{{../11_figures/{rel_path}}}\n"
        f"  \\caption{{{_escape_latex(spec_caption)}}}\n"
        f"  \\label{{fig:{fig.figure_id}}}\n"
        f"\\end{{figure}}\n"
    )


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------


def _build_bibliography(pool: list[CitationEntry]) -> tuple[str, str]:
    """Returns (bibliography LaTeX block, references.bib content)."""
    bib_entries: list[str] = []
    for entry in pool:
        bib_entries.append(entry.bibtex_line())

    bib_content = "\n\n".join(bib_entries)
    latex_block = (
        "\\bibliographystyle{IEEEtran}\n"
        "\\bibliography{references}\n"
    )
    return latex_block, bib_content


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------


def assemble_manuscript(
    plan: EditorPlan,
    sections: list[SectionDraft],
    figures: list[FigureResult],
    context: EditorContext,
) -> tuple[str, str]:
    """
    Returns (main_tex, references_bib).

    Sections are rendered in plan order. Figures are inserted at end of
    the Results section body or as a block before References.
    """
    tex_parts: list[str] = []

    # Preamble
    tex_parts.append(_preamble(
        plan.article_title or context.title,
        context.authors,
        plan.ieee_format,
    ))

    # Draft lookup by section_id
    draft_map = {d.section_id: d for d in sections}
    figure_map = {f.figure_id: f for f in figures}
    figure_spec_map = {s.figure_id: s for s in plan.figures}

    # Render sections; each figure environment appears at most once (first referencing section).
    rendered_figure_ids: set[str] = set()
    body_order = 0
    for spec in plan.ordered_sections:
        draft = draft_map.get(spec.section_id)
        if draft is None:
            tex_parts.append(f"% Section '{spec.heading}' was not generated.\n")
            continue

        sid_lower = spec.section_id.lower()
        if sid_lower not in ("abstract", "index_terms"):
            body_order += 1

        rendered = _render_section(draft, body_order)
        tex_parts.append(rendered)

        for fig_spec in sorted(plan.figures, key=lambda f: f.order):
            if fig_spec.figure_id in rendered_figure_ids:
                continue
            if fig_spec.figure_id not in (draft.figures_referenced or []):
                continue
            fig_result = figure_map.get(fig_spec.figure_id)
            if fig_result is not None:
                tex_parts.append(
                    _render_figure(fig_result, fig_spec.caption, fig_spec.order)
                )
                rendered_figure_ids.add(fig_spec.figure_id)

    # Figures never referenced in text — append once at end (before bibliography)
    for fig_spec in sorted(plan.figures, key=lambda f: f.order):
        if fig_spec.figure_id in rendered_figure_ids:
            continue
        fig_result = figure_map.get(fig_spec.figure_id)
        if fig_result is not None:
            tex_parts.append(_render_figure(fig_result, fig_spec.caption, fig_spec.order))
            rendered_figure_ids.add(fig_spec.figure_id)

    # Bibliography
    bib_block, bib_content = _build_bibliography(context.citation_pool)
    tex_parts.append(bib_block)
    tex_parts.append(r"\end{document}" + "\n")

    return "\n".join(tex_parts), bib_content
