"""Generate AutoPaper pipeline flow diagram as PDF."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def _box(ax, x, y, w, h, text, fc="#E8F0FE", ec="#1a56db", fontsize=8):
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize)


def _arrow(ax, x1, y1, x2, y2, color="#333", rad=0.0, lw=1.3, style="-|>"):
    arr = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle=style,
        mutation_scale=13,
        linewidth=lw,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(arr)


def _loop(ax, points, color="#7B1FA2", label=""):
    """Draw closed loop through list of (x,y) points."""
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        style = "-|>" if i == len(points) - 2 else "-"
        arr = FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle=style,
            mutation_scale=13,
            linewidth=1.4,
            color=color,
            linestyle="--" if i < len(points) - 2 else "-",
        )
        ax.add_patch(arr)
    if label:
        lx = sum(p[0] for p in points) / len(points)
        ly = max(p[1] for p in points) + 0.25
        ax.text(lx, ly, label, ha="center", fontsize=7.5, color=color, fontweight="bold")


def main() -> Path:
    fig, ax = plt.subplots(figsize=(13, 22))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 28)
    ax.axis("off")
    fig.suptitle("AutoPaper — Current Pipeline Flow", fontsize=17, fontweight="bold", y=0.98)

    cx = 6.5  # center column

    # ── Entry ─────────────────────────────────────────────────────────────
    ax.text(cx, 27.0, "Entry", fontsize=10, fontweight="bold", ha="center", color="#555")
    _box(ax, 3.2, 26.0, 3.8, 0.85, "FastAPI\nPOST /api/runs", fc="#FFF3E0", ec="#E65100")
    _box(ax, 9.8, 26.0, 4.0, 0.85, "CLI  autopaper --input …\n--full-research --ieee-edit", fc="#FFF3E0", ec="#E65100")
    _box(ax, cx, 24.7, 5.0, 0.75, "Subprocess: python -m autopaper.main.app", fc="#FFF8E1", ec="#F9A825")
    _arrow(ax, 3.2, 25.55, cx, 25.1)
    _arrow(ax, 9.8, 25.55, cx, 25.1)
    _arrow(ax, cx, 24.3, cx, 23.75)

    # ── Stage 1 ───────────────────────────────────────────────────────────
    ax.text(cx, 23.35, "STAGE 1 — Input  (01–04)  ·  Gemini agents", fontsize=11, fontweight="bold", ha="center", color="#1565C0")
    s1 = [
        (cx, 22.6, "01  Disk ingest\n01_raw_input_bundle.json"),
        (cx, 21.5, "02  Text Parser\n02_cleaned_text.json"),
        (cx, 20.4, "03  Vision Agent\n03_cleaned_images.json"),
        (cx, 19.3, "04  Joiner Agent\n04_final_standardized.json"),
    ]
    for x, y, t in s1:
        _box(ax, x, y, 4.6, 0.75, t)
    for i in range(len(s1) - 1):
        _arrow(ax, cx, s1[i][1] - 0.42, cx, s1[i + 1][1] + 0.42)
    _box(ax, 10.5, 20.4, 3.0, 0.75, "Abort if image\nunreadable", fc="#FFEBEE", ec="#C62828", fontsize=7)
    _box(ax, 10.5, 19.3, 3.0, 0.85, "Mismatch policy\n(TTY prompt / strict / force)", fc="#FFEBEE", ec="#C62828", fontsize=7)
    _arrow(ax, 8.3, 20.4, 9.0, 20.4)
    _arrow(ax, 8.3, 19.3, 9.0, 19.3)
    _arrow(ax, cx, 18.88, cx, 18.35)

    # ── Stage 2 ───────────────────────────────────────────────────────────
    ax.text(cx, 17.95, "STAGE 2 — Research  (05–08)", fontsize=11, fontweight="bold", ha="center", color="#1565C0")
    _box(ax, cx, 17.2, 5.0, 0.85, "05  Orchestrator plan  (OpenAI GPT, tools)\n05_orchestrator_plan.json", fc="#E8EAF6", ec="#3949AB")
    _arrow(ax, cx, 16.77, cx, 16.25)
    _box(ax, cx, 15.75, 5.3, 0.85, "06  Parallel search  (Gemini)\ngemini_search + openai_search → 06_research/", fc="#E8EAF6", ec="#3949AB")
    _arrow(ax, cx, 15.32, cx, 14.8)
    _box(ax, cx, 14.3, 4.8, 0.75, "07  Validator per task  (Gemini)\n07_validation/", fc="#E8EAF6", ec="#3949AB")

    # Research follow-up loop (left side)
    _loop(
        ax,
        [
            (1.5, 14.3),   # left of validator
            (1.5, 15.75),  # up to search level
            (3.8, 15.75),  # into search box
            (3.8, 14.3),   # back down
            (4.5, 14.3),   # into validator
        ],
        color="#7B1FA2",
        label="↺ Follow-up loop (Gemini followup.md)\ncoverage gaps → new 06 tasks\nRESEARCH_FOLLOWUP_ROUNDS (default 1)",
    )
    _box(ax, 1.5, 13.2, 3.0, 0.65, "05_orchestrator\n_followups.json", fc="#F3E5F5", ec="#7B1FA2", fontsize=7)
    _arrow(ax, 1.5, 13.55, 1.5, 13.9, color="#7B1FA2")

    _arrow(ax, cx, 13.92, cx, 13.4)
    _box(ax, cx, 12.9, 4.8, 0.75, "08  Research index catalog  (Gemini)\n08_research_index.md", fc="#E8EAF6", ec="#3949AB")
    _arrow(ax, cx, 12.52, cx, 11.95)

    # ── Stage 3 ───────────────────────────────────────────────────────────
    ax.text(cx, 11.55, "STAGE 3 — Editor  (09–13)", fontsize=11, fontweight="bold", ha="center", color="#1565C0")
    _box(ax, cx, 10.85, 4.5, 0.65, "Load context (04, 06, 07, 08)")
    _arrow(ax, cx, 10.52, cx, 10.05)
    _box(ax, cx, 9.55, 5.0, 0.85, "09  Editor Orchestrator  (OpenAI GPT)\n09_editor_plan.json + plan enrich", fc="#E0F2F1", ec="#00695C")
    _arrow(ax, cx, 9.12, cx, 8.65)
    _box(ax, cx, 8.15, 5.0, 0.75, "10  Section Writer ×8  (Gemini, parallel)\n10_sections/", fc="#E0F2F1", ec="#00695C")
    _arrow(ax, cx, 7.77, cx, 7.3)
    _box(ax, cx, 6.8, 5.1, 0.75, "11  Figure Agent  (Gemini + matplotlib)\n11_figures/", fc="#E0F2F1", ec="#00695C")

    # Figure retry micro-loop
    _loop(
        ax,
        [
            (10.3, 6.8),
            (11.2, 6.8),
            (11.2, 7.15),
            (10.3, 7.15),
            (10.3, 6.95),
        ],
        color="#C62828",
        label="retry",
    )

    _arrow(ax, cx, 6.42, cx, 5.95)
    _box(ax, cx, 5.45, 5.2, 0.85, "12  IEEE Validator  (Gemini + deterministic)\n12_editor_validation/", fc="#E0F2F1", ec="#00695C")

    # Section rewrite loop (right side)
    _loop(
        ax,
        [
            (11.8, 5.45),
            (11.8, 8.15),
            (9.5, 8.15),
            (9.5, 5.45),
            (10.2, 5.45),
        ],
        color="#7B1FA2",
        label="↺ Rewrite loop\nscore < threshold →\nre-call Section Writer\n(max attempts)",
    )

    _arrow(ax, cx, 5.02, cx, 4.55)
    _box(ax, cx, 4.05, 4.8, 0.75, "Integrity check (warn → continue)", fc="#FFFDE7", ec="#F57F17")
    _arrow(ax, cx, 3.67, cx, 3.2)
    _box(ax, cx, 2.7, 4.8, 0.75, "Assemble LaTeX → 13_ieee_manuscript/main.tex", fc="#E0F2F1", ec="#00695C")
    _arrow(ax, cx, 2.32, cx, 1.85)
    _box(ax, cx, 1.35, 5.0, 0.75, "Compile PDF  (pdflatex ×3)\nmain.pdf", fc="#C8E6C9", ec="#2E7D32", fontsize=9)

    # Footer legend
    ax.text(
        0.35,
        0.35,
        "Output: output/execution_NNN/   |   API stream: GET /api/runs/{id}/stream (SSE)\n"
        "GPT (OpenAI): research + editor orchestrators only   |   Gemini: all other agents\n"
        "Purple dashed arrows = conditional loops   |   Regenerate: python scripts/generate_pipeline_flow_pdf.py",
        fontsize=7.5,
        va="bottom",
        color="#444",
    )

    out_dir = Path(__file__).resolve().parents[1] / "docs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "autopaper_pipeline_flow.pdf"
    fig.savefig(out_path, format="pdf", bbox_inches="tight", dpi=150)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    print(main())
