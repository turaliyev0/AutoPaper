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
from .plan_filters import filter_editor_plan_figures
from .run_log import RunLog
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
        verbose_log: bool = True,
    ) -> EditorRunResult:
        errors: list[str] = []
        log = RunLog(execution_dir, verbose=verbose_log)
        log.header(execution_dir, ieee_format)

        # ── STEP 1: Load context ────────────────────────────────────────
        context: EditorContext | None = None
        with log.step("Load context"):
            try:
                context = load_editor_context(execution_dir, ieee_format=ieee_format)
                log.log_context(context)
            except FileNotFoundError as exc:
                log.fail(str(exc))
                log.footer(EditorRunResult(errors=[str(exc)]))
                return EditorRunResult(errors=[str(exc)])

        # ── STEP 2: Editor Orchestrator ────────────────────────────────
        plan: EditorPlan | None = None
        with log.step(
            "Editor Orchestrator",
            agent=f"OpenAI {self._settings.editor_orchestrator_model}",
        ):
            log.arrow("Calling OpenAI Responses API (tool session)…")
            try:
                plan = await self._orchestrator.create_plan(context)
                plan = filter_editor_plan_figures(plan, context)
                log.log_plan(plan)
                write_editor_plan(execution_dir, plan)
                log.ok("09_editor_plan.json written")
            except Exception as exc:
                log.fail(f"Orchestrator failed: {exc}")
                errors.append(f"Orchestrator failed: {exc}")
                log.footer(EditorRunResult(errors=errors))
                return EditorRunResult(errors=errors)

        # ── STEP 3: Section Writing ────────────────────────────────────
        sections: list = []
        with log.step(
            f"Section Writing ({len(plan.sections)} sections, parallel)",
            agent=f"OpenAI {self._settings.editor_section_writer_model}",
        ):
            try:
                sections = await self._coordinator.write_all(plan, context)
                log.log_sections(sections)
                write_sections(execution_dir, sections)
                ok_count = sum(1 for s in sections if s.success)
                log.ok(f"{ok_count}/{len(sections)} sections written → 10_sections/")
                if ok_count < len(sections):
                    failed = ", ".join(s.section_id for s in sections if not s.success)
                    errors.append(f"{len(sections) - ok_count} section(s) failed: {failed}")
            except Exception as exc:
                log.fail(f"Section coordinator failed: {exc}")
                errors.append(f"Section writing failed: {exc}")

        # ── STEP 4: Figure Generation ──────────────────────────────────
        figures: list[FigureResult] = []
        fig_spec_map = {s.figure_id: s for s in plan.figures}
        with log.step(
            f"Figure Generation ({len(plan.figures)} figures)",
            agent=f"OpenAI {self._settings.editor_figure_model} + matplotlib subprocess",
        ):
            figures_dir = execution_dir / "11_figures"
            figures_dir.mkdir(parents=True, exist_ok=True)
            for fig_spec in plan.figures:
                log.arrow(f"Generating {fig_spec.figure_id} …")
                result = await self._figure_agent.generate(fig_spec, figures_dir, context)
                figures.append(result)
                if result.success:
                    log.ok(f"{fig_spec.figure_id}: done (retries={result.retries})")
                else:
                    log.fail(f"{fig_spec.figure_id}: {(result.error or '')[:80]}")
                    errors.append(f"Figure '{fig_spec.figure_id}' failed: {result.error}")
            log.log_figures(figures, fig_spec_map)
            if figures:
                write_figures(execution_dir, figures)
                ok_f = sum(1 for f in figures if f.success)
                log.ok(f"{ok_f}/{len(figures)} figures → 11_figures/")

        # ── STEP 5: IEEE Validation ────────────────────────────────────
        validation: list = []
        with log.step(
            "IEEE Validation",
            agent=f"Gemini {self._settings.default_gemini_model} + deterministic checks",
        ):
            if sections:
                try:
                    validation = await self._validator.validate_all(sections, plan, context)
                    log.log_validation(validation)
                    write_editor_validation(execution_dir, validation)
                    v_pass = sum(1 for v in validation if v.verdict == "pass")
                    v_warn = sum(1 for v in validation if v.verdict == "warn")
                    v_fail = sum(1 for v in validation if v.verdict == "fail")
                    log.ok(f"Results: {v_pass} pass / {v_warn} warn / {v_fail} fail → 12_editor_validation/")
                except Exception as exc:
                    log.fail(f"Validator failed: {exc}")
                    errors.append(f"Validation failed: {exc}")
            else:
                log.warn("No sections to validate.")

        # ── STEP 6: Assemble LaTeX ─────────────────────────────────────
        manuscript_tex = ""
        bib_content = ""
        with log.step("Assemble LaTeX (IEEEtran)"):
            try:
                manuscript_tex, bib_content = assemble_manuscript(plan, sections, figures, context)
                write_manuscript(execution_dir, main_tex=manuscript_tex, references_bib=bib_content)
                lines = manuscript_tex.count("\n")
                bib_entries = bib_content.count("@article")
                log.ok(f"main.tex written ({lines} lines)")
                log.ok(f"references.bib written ({bib_entries} entries)")
                log.ok("→ 13_ieee_manuscript/")
            except Exception as exc:
                log.fail(f"Assembler failed: {exc}")
                errors.append(f"Assembler failed: {exc}")

        # ── STEP 7: Compile PDF ────────────────────────────────────────
        pdf_path = ""
        with log.step("Compile PDF (pdflatex → bibtex → pdflatex × 2)"):
            if manuscript_tex:
                ms_dir = execution_dir / "13_ieee_manuscript"
                log.arrow("Pass 1: pdflatex …")
                ok_compile, msg = compile_pdf(ms_dir)
                if ok_compile:
                    pdf_path = str(ms_dir / "main.pdf")
                    from pathlib import Path as _P
                    kb = round(_P(pdf_path).stat().st_size / 1024, 1)
                    log.ok(f"main.pdf compiled ({kb} KB)")
                    log.ok(f"→ {pdf_path}")
                else:
                    log.fail(msg)
                    errors.append(msg)
            else:
                log.warn("No manuscript to compile.")

        result = EditorRunResult(
            plan=plan,
            sections=sections,
            figures=figures,
            validation=validation,
            manuscript_tex=manuscript_tex,
            pdf_path=pdf_path,
            errors=errors,
        )
        log.footer(result)
        return result


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
    verbose_log: bool = True,
) -> EditorRunResult:
    """
    Synchronous entry point.

    Always compiles to PDF at the end.
    Run log written to ``execution_dir/editor_run.log`` and mirrored to stderr.
    Set ``verbose_log=False`` to suppress stderr output (log still written to disk).
    """
    settings = load_editor_settings(env_path)
    pipeline = EditorPipeline(settings)
    return asyncio.run(pipeline.run(execution_dir, ieee_format=ieee_format, verbose_log=verbose_log))
