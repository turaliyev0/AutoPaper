"""EditorPipeline — orchestrates all editor agents end-to-end."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

from research.clients.gemini_client import GeminiClient
from research.clients.openai_client import OpenAIClient

from .agents.figure_agent import FigureAgent
from .agents.ieee_validator import IeeeValidatorAgent
from .agents.orchestrator import EditorOrchestratorAgent
from .agents.section_writer import SectionCoordinator, SectionWriterAgent
from .assembler import assemble_manuscript
from .config import EditorSettings, load_editor_settings
from .context import EditorContext, load_editor_context
from .schemas import EditorPlan, EditorRunResult, FigureResult, IeeeFormat
from .storage import (
    write_editor_plan,
    write_editor_validation,
    write_figures,
    write_manuscript,
    write_sections,
)

logger = logging.getLogger(__name__)


class EditorPipeline:
    """
    Full editor pipeline:

    1. Load :class:`EditorContext` from execution dir (04, 06, 07, 08)
    2. :class:`EditorOrchestratorAgent` → :class:`EditorPlan` (09)
    3. :class:`SectionCoordinator` → parallel section drafts (10)
    4. :class:`FigureAgent` → figure code + images (11)
    5. :class:`IeeeValidatorAgent` → per-section validation (12)
    6. :func:`assemble_manuscript` → main.tex (13)
    """

    def __init__(self, settings: EditorSettings) -> None:
        settings.validate_keys()
        self._settings = settings

        openai_client = OpenAIClient(
            settings,  # type: ignore[arg-type]  # EditorSettings has orchestrator_api_key shim
            api_key=settings.openai_key,
            model=settings.editor_orchestrator_model,
        )
        gemini_client = GeminiClient(
            settings,  # type: ignore[arg-type]  # EditorSettings has gemini_search_api_key shim
            api_key=settings.gemini_key,
            model=settings.editor_validator_model,
        )
        writer_client = OpenAIClient(
            settings,  # type: ignore[arg-type]
            api_key=settings.openai_key,
            model=settings.editor_section_writer_model,
        )
        figure_client = OpenAIClient(
            settings,  # type: ignore[arg-type]
            api_key=settings.openai_key,
            model=settings.editor_figure_model,
        )

        self._orchestrator = EditorOrchestratorAgent(openai_client, settings=settings)
        self._coordinator = SectionCoordinator(SectionWriterAgent(writer_client))
        self._validator = IeeeValidatorAgent(gemini_client)
        self._figure_agent = FigureAgent(figure_client, settings)

    async def run(
        self,
        execution_dir: Path,
        *,
        ieee_format: IeeeFormat = "journal",
    ) -> EditorRunResult:
        errors: list[str] = []

        # --- load context ---
        try:
            context = load_editor_context(execution_dir, ieee_format=ieee_format)
        except FileNotFoundError as exc:
            return EditorRunResult(errors=[str(exc)])

        # --- orchestrate plan ---
        try:
            plan = await self._orchestrator.create_plan(context)
        except Exception as exc:
            logger.error("Editor orchestrator failed: %s", exc)
            return EditorRunResult(errors=[f"Orchestrator failed: {exc}"])

        write_editor_plan(execution_dir, plan)
        logger.info("Editor plan written to 09_editor_plan.json")

        # --- write sections ---
        try:
            sections = await self._coordinator.write_all(plan, context)
        except Exception as exc:
            logger.error("Section coordinator failed: %s", exc)
            errors.append(f"Section writing failed: {exc}")
            sections = []

        if sections:
            write_sections(execution_dir, sections)
            ok = sum(1 for s in sections if s.success)
            logger.info("Sections: %d/%d succeeded", ok, len(sections))
            if ok < len(sections):
                errors.append(
                    f"{len(sections) - ok} section(s) failed: "
                    + ", ".join(s.section_id for s in sections if not s.success)
                )

        # --- generate figures ---
        figures_dir = execution_dir / "11_figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        figures: list[FigureResult] = []
        for fig_spec in plan.figures:
            result = await self._figure_agent.generate(fig_spec, figures_dir, context)
            figures.append(result)
            if not result.success:
                errors.append(f"Figure '{fig_spec.figure_id}' failed: {result.error}")

        if figures:
            write_figures(execution_dir, figures)

        # --- validate sections ---
        validation = []
        if sections:
            try:
                validation = await self._validator.validate_all(sections, plan, context)
                write_editor_validation(execution_dir, validation)
            except Exception as exc:
                logger.error("IEEE validator failed: %s", exc)
                errors.append(f"Validation failed: {exc}")

        # --- assemble LaTeX ---
        manuscript_tex = ""
        bib_content = ""
        try:
            manuscript_tex, bib_content = assemble_manuscript(plan, sections, figures, context)
            write_manuscript(execution_dir, main_tex=manuscript_tex, references_bib=bib_content)
            logger.info("Manuscript written to 13_ieee_manuscript/main.tex")
        except Exception as exc:
            logger.error("Assembler failed: %s", exc)
            errors.append(f"Assembler failed: {exc}")

        # --- compile PDF (always) ---
        pdf_path = ""
        if manuscript_tex:
            ms_dir = execution_dir / "13_ieee_manuscript"
            ok, msg = compile_pdf(ms_dir)
            logger.info("PDF: %s", msg)
            if ok:
                pdf_path = str(ms_dir / "main.pdf")
            else:
                errors.append(msg)

        return EditorRunResult(
            plan=plan,
            sections=sections,
            figures=figures,
            validation=validation,
            manuscript_tex=manuscript_tex,
            pdf_path=pdf_path,
            errors=errors,
        )


def compile_pdf(manuscript_dir: Path) -> tuple[bool, str]:
    """
    Compile ``main.tex`` → ``main.pdf`` using pdflatex if available.

    Returns (success, message).
    """
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return False, "pdflatex not found in PATH; skipping PDF compilation."

    tex_file = manuscript_dir / "main.tex"
    if not tex_file.is_file():
        return False, "main.tex not found."

    def _run(extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
        cmd = [
            pdflatex,
            "-interaction=batchmode",
            "--enable-installer",
            "main.tex",
        ]
        if extra_args:
            cmd = [pdflatex] + extra_args + ["main.tex"]
        return subprocess.run(cmd, cwd=manuscript_dir, capture_output=True, text=True, timeout=120)

    try:
        # Pass 1
        _run()
        # BibTeX pass
        bibtex = shutil.which("bibtex")
        if bibtex:
            subprocess.run([bibtex, "main"], cwd=manuscript_dir, capture_output=True, timeout=30)
        # Pass 2 + 3
        _run()
        r = _run()

        pdf_path = manuscript_dir / "main.pdf"
        if pdf_path.is_file():
            size_kb = round(pdf_path.stat().st_size / 1024, 1)
            return True, f"PDF compiled: main.pdf ({size_kb} KB)"
        return False, f"pdflatex exited {r.returncode} but no PDF produced.\n{r.stdout[-500:]}"
    except subprocess.TimeoutExpired:
        return False, "pdflatex timed out."
    except Exception as exc:
        return False, f"PDF compilation error: {exc}"


def run_editor_pipeline(
    execution_dir: Path,
    *,
    ieee_format: IeeeFormat = "journal",
    env_path: Path | None = None,
) -> EditorRunResult:
    """Synchronous entry point. Always compiles to PDF at the end."""
    settings = load_editor_settings(env_path)
    pipeline = EditorPipeline(settings)
    return asyncio.run(pipeline.run(execution_dir, ieee_format=ieee_format))
