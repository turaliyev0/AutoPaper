#!/usr/bin/env python3
"""Generate docs/pipeline_flow.pdf — current AutoPaper end-to-end flow."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "pipeline_flow.pdf"

Box = tuple[float, float, float, float]


def _box(ax, rect: Box, text: str, *, face: str, edge: str = "#333", fontsize: float = 8) -> None:
    x, y, w, h = rect
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.008,rounding_size=0.012",
        linewidth=1.1,
        edgecolor=edge,
        facecolor=face,
        transform=ax.transAxes,
        zorder=2,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        transform=ax.transAxes,
        zorder=3,
        linespacing=1.25,
    )


def _arrow(ax, p0: tuple[float, float], p1: tuple[float, float], *, color: str = "#444") -> None:
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.0,
        color=color,
        transform=ax.transAxes,
        zorder=1,
    )
    ax.add_patch(arr)


def _cx(rect: Box) -> float:
    return rect[0] + rect[2] / 2


def _top(rect: Box) -> float:
    return rect[1] + rect[3]


def _bot(rect: Box) -> float:
    return rect[1]


def build_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.5, 14))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.5, 0.99, "AutoPaper Pipeline Flow", ha="center", fontsize=15, fontweight="bold")
    ax.text(
        0.5,
        0.975,
        "Upload → input (01–04) → research (05–08) → editor (09–13) → PDF",
        ha="center",
        fontsize=8.5,
        color="#555",
    )

    cx, w = 0.5, 0.86
    x0 = cx - w / 2
    h_step = 0.038
    gap = 0.012
    y = 0.945

    def step(label: str, face: str = "#f8fafc", fs: float = 7.5) -> Box:
        nonlocal y
        rect = (x0, y - h_step, w, h_step)
        _box(ax, rect, label, face=face, fontsize=fs)
        y -= h_step + gap
        return rect

    def header(title: str, face: str) -> Box:
        nonlocal y
        h = 0.032
        rect = (x0, y - h, w, h)
        _box(ax, rect, title, face=face, fontsize=9)
        y -= h + gap
        return rect

    entry = step("ENTRY: POST /api/runs  ·  CLI autopaper  →  output/execution_NNN/", face="#e0f2fe", fs=8)

    h1 = header("STAGE 1 — Input (Gemini)", "#bfdbfe")
    b01 = step("01  Disk ingest  →  01_raw_input_bundle.json")
    b02 = step("02  Text parser  →  02_cleaned_text.json")
    b03 = step("03  Vision agent  →  03_cleaned_images.json")
    b04 = step("04  Joiner  →  04_final_standardized.json")
    gate = step(
        "Completeness gate: gaps → 04_input_gaps.json · awaiting_input · supplement → resume",
        face="#fef9c3",
        fs=7,
    )

    h2 = header("STAGE 2 — Research", "#bbf7d0")
    b05 = step("05  OpenAI GPT orchestrator  →  05_orchestrator_plan.json")
    b06 = step("06  Parallel search (Gemini): gemini_search + openai_search  →  06_research/")
    b07 = step("07  Claude validator (per task)  →  07_validation/")
    b08a = step("     Optional follow-up round (Gemini plan + search + Claude validate)", fs=7)
    b08 = step("08  Gemini research index  →  08_research_index.md")

    h3 = header("STAGE 3 — Editor", "#ddd6fe")
    b09 = step("09  OpenAI GPT editor plan  →  09_editor_plan.json")
    row_y = y
    h_split = 0.038
    left = (x0, row_y - h_split, w * 0.48, h_split)
    right = (x0 + w * 0.52, row_y - h_split, w * 0.48, h_split)
    _box(ax, left, "10  Gemini section writer  →  10_sections/", face="#faf5ff", fontsize=7)
    _box(ax, right, "11  Gemini figure agent  →  11_figures/", face="#faf5ff", fontsize=7)
    y = row_y - h_split - gap

    qa = step(
        "12  Claude holistic manuscript QA + coordinated rewrites  →  12_editor_validation/",
        face="#fce7f3",
        fs=7,
    )
    pdf = step("13  Assemble LaTeX + pdflatex  →  13_ieee_manuscript/main.pdf", face="#e0e7ff", fs=7.5)
    api = step("API: GET /api/runs/{id}/pdf  ·  /research  ·  SSE /stream", face="#e0f2fe", fs=7.5)

    # Arrows (main spine)
    chain = [entry, h1, b01, b02, b03, b04, gate, h2, b05, b06, b07, b08a, b08, h3, b09, qa, pdf, api]
    for a, b in zip(chain, chain[1:]):
        _arrow(ax, (_cx(a), _bot(a)), (_cx(b), _top(b)))

    _arrow(ax, (_cx(b09), _bot(b09)), (_cx(left), _top(left)), color="#666")
    _arrow(ax, (_cx(b09), _bot(b09)), (_cx(right), _top(right)), color="#666")
    _arrow(ax, (_cx(left), _bot(left)), (_cx(qa), _top(qa)), color="#666")
    _arrow(ax, (_cx(right), _bot(right)), (_cx(qa), _top(qa)), color="#666")

    ax.text(
        0.5,
        0.018,
        "OpenAI = orchestrators  |  Gemini = search, sections, figures, index  |  Claude = research validator + manuscript QA",
        ha="center",
        fontsize=7,
        color="#555",
    )
    ax.text(
        0.5,
        0.006,
        "Env: OPENAI_API_KEY · GOOGLE_API_KEY · ANTHROPIC_API_KEY",
        ha="center",
        fontsize=6.5,
        color="#777",
    )

    fig.savefig(path, format="pdf", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Wrote {path}")


if __name__ == "__main__":
    build_pdf(OUT)
