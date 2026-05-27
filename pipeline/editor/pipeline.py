"""EditorPipeline — orchestrates all editor agents end-to-end."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

from pipeline.research.clients.gemini_client import GeminiClient
from pipeline.research.clients.openai_client import OpenAIClient

from .agents.figure_agent import FigureAgent
from .agents.ieee_validator import IeeeValidatorAgent
from .agents.orchestrator import EditorOrchestratorAgent
from .agents.section_writer import SectionCoordinator, SectionWriterAgent
from .assembler import assemble_manuscript
from .config import EditorSettings, load_editor_settings
from .context import EditorContext, load_editor_context
from .plan_filters import filter_editor_plan_figures
from .integrity_check import validate_manuscript_integrity
from .plan_validate import validate_editor_plan
from .run_log import RunLog
from .schemas import EditorPlan, EditorRunResult, FigureResult, IeeeFormat
from .storage import (
    EXEC_EDITOR_PLAN,
    EXEC_FIGURES_DIR,
    EXEC_SECTIONS_DIR,
    figure_result_if_complete,
    load_editor_plan,
    load_editor_validation,
    load_section_drafts,
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
        writer_client = GeminiClient(
            settings,  # type: ignore[arg-type]
            api_key=settings.gemini_key,
            model=settings.section_writer_model,
        )
        figure_client = GeminiClient(
            settings,  # type: ignore[arg-type]
            api_key=settings.gemini_key,
            model=settings.figure_model,
        )

        self._orchestrator = EditorOrchestratorAgent(openai_client, settings=settings)
        self._writer = SectionWriterAgent(writer_client)
        self._coordinator = SectionCoordinator(self._writer)
        self._validator = IeeeValidatorAgent(gemini_client)
        self._figure_agent = FigureAgent(figure_client, settings)

    async def run(
        self,
        execution_dir: Path,
        *,
        ieee_format: IeeeFormat = "journal",
        verbose_log: bool = True,
        resume: bool = False,
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
                errors.append(str(exc))
                result = EditorRunResult(errors=errors)
                log.footer(result)
                return result

        # ── STEP 2: Editor Orchestrator ────────────────────────────────
        plan: EditorPlan | None = None
        if resume and (execution_dir / EXEC_EDITOR_PLAN).is_file():
            plan = load_editor_plan(execution_dir)
            if plan is not None:
                plan = filter_editor_plan_figures(plan, context)
                validate_editor_plan(plan, context)
                with log.step("Editor Orchestrator (resumed)"):
                    log.ok(f"Loaded existing {EXEC_EDITOR_PLAN} ({len(plan.sections)} sections, {len(plan.figures)} figures)")

        if plan is None:
            with log.step(
                "Editor Orchestrator",
                agent=f"OpenAI {self._settings.editor_orchestrator_model}",
            ):
                print("[STEP] Planning manuscript structure", flush=True)
                log.arrow("Calling OpenAI Responses API (tool session)…")
                try:
                    plan = await self._orchestrator.create_plan(context)
                    plan = filter_editor_plan_figures(plan, context)
                    validate_editor_plan(plan, context)
                    log.log_plan(plan)
                    write_editor_plan(execution_dir, plan)
                    log.ok("09_editor_plan.json written")
                except Exception as exc:
                    log.fail(f"Orchestrator failed: {exc}")
                    errors.append(f"Orchestrator failed: {exc}")
                    result = EditorRunResult(errors=errors)
                    log.footer(result)
                    return result

        # ── STEP 3: Section Writing ────────────────────────────────────
        sections: list = []
        resumed_sections = resume and (execution_dir / EXEC_SECTIONS_DIR / "manifest.json").is_file()
        if resumed_sections:
            sections = load_section_drafts(execution_dir)
            ok_count = sum(1 for s in sections if s.success)
            with log.step(f"Section Writing (resumed, {len(sections)} sections)"):
                log.ok(f"Loaded {ok_count}/{len(sections)} sections from {EXEC_SECTIONS_DIR}/")
                if ok_count < len(plan.sections):
                    errors.append(
                        f"Resume: only {ok_count}/{len(plan.sections)} section drafts on disk.",
                    )
        else:
            with log.step(
                f"Section Writing ({len(plan.sections)} sections, parallel)",
                agent=f"Gemini {self._settings.section_writer_model}",
            ):
                print(f"[STEP] Writing {len(plan.sections)} section(s)", flush=True)
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
            agent=f"Gemini {self._settings.figure_model} + matplotlib subprocess",
        ):
            print(f"[STEP] Generating {len(plan.figures)} figure(s)", flush=True)
            figures_dir = execution_dir / "11_figures"
            figures_dir.mkdir(parents=True, exist_ok=True)
            for idx, fig_spec in enumerate(plan.figures):
                if idx > 0:
                    await asyncio.sleep(2.0)
                existing = figure_result_if_complete(figures_dir, fig_spec.figure_id)
                if existing is not None:
                    log.arrow(f"Skipping {fig_spec.figure_id} (PNG already on disk)")
                    figures.append(existing)
                    log.ok(f"{fig_spec.figure_id}: resumed from disk")
                    continue
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
            print("[STEP] Validating IEEE format compliance", flush=True)
            if sections:
                try:
                    loaded_val = load_editor_validation(execution_dir) if resume else []
                    done_ids = {v.section_id for v in loaded_val}
                    if resume and len(done_ids) >= len(sections):
                        validation = loaded_val
                        log.ok(f"Resumed {len(validation)} validation results from 12_editor_validation/")
                    else:
                        pending = (
                            [s for s in sections if s.section_id not in done_ids]
                            if resume
                            else sections
                        )
                        if resume and loaded_val:
                            log.arrow(
                                f"Validating {len(pending)} remaining section(s) "
                                f"({len(loaded_val)} already on disk)",
                            )
                        threshold = self._settings.editor_validator_score_threshold
                        max_rw = self._settings.editor_validator_rewrite_max_attempts
                        new_val, rewritten = await self._validator.validate_all_with_rewrites(
                            pending,
                            plan,
                            context,
                            self._writer,
                            threshold=threshold,
                            max_rewrites=max_rw,
                            run_dir=execution_dir,
                            persist_each=True,
                        )
                        if any(r.rewrite_attempts > 0 for r in new_val):
                            by_id = {s.section_id: s for s in sections}
                            for d in rewritten:
                                by_id[d.section_id] = d
                            sections = [
                                by_id[sp.section_id]
                                for sp in plan.ordered_sections
                                if sp.section_id in by_id
                            ]
                            write_sections(execution_dir, sections)
                            n_rw = sum(1 for r in new_val if r.rewrite_attempts > 0)
                            log.ok(f"Rewrote {n_rw} section(s) after low validator score (<{threshold})")
                        validation = loaded_val + new_val
                        write_editor_validation(execution_dir, validation)
                    log.log_validation(
                        validation,
                        threshold=self._settings.editor_validator_score_threshold,
                    )
                    v_pass = sum(1 for v in validation if v.verdict == "pass")
                    v_warn = sum(1 for v in validation if v.verdict == "warn")
                    v_fail = sum(1 for v in validation if v.verdict == "fail")
                    log.ok(f"Results: {v_pass} pass / {v_warn} warn / {v_fail} fail → 12_editor_validation/")
                except Exception as exc:
                    log.fail(f"Validator failed: {exc}")
                    errors.append(f"Validation failed: {exc}")
            else:
                log.warn("No sections to validate.")

        # ── STEP 5b: Integrity gate ───────────────────────────────────
        integrity_ok = True
        with log.step("Manuscript integrity check"):
            if sections and plan is not None:
                try:
                    validate_manuscript_integrity(plan, sections, context)
                    log.ok("Integrity checks passed")
                except ValueError as exc:
                    integrity_ok = False
                    log.fail(str(exc))
                    errors.append(str(exc))
            else:
                log.warn("Skipping integrity check (no sections or plan).")

        # ── STEP 6: Assemble LaTeX ─────────────────────────────────────
        manuscript_tex = ""
        bib_content = ""
        with log.step("Assemble LaTeX (IEEEtran)"):
            print("[STEP] Assembling LaTeX manuscript", flush=True)
            if not integrity_ok:
                log.warn("Skipping assembly — integrity check failed.")
            elif not sections:
                log.warn("No sections to assemble.")
            else:
                try:
                    manuscript_tex, bib_content = assemble_manuscript(
                        plan, sections, figures, context
                    )
                    write_manuscript(
                        execution_dir,
                        main_tex=manuscript_tex,
                        references_bib=bib_content,
                    )
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
            print("[STEP] Compiling PDF", flush=True)
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
    resume: bool = False,
) -> EditorRunResult:
    """
    Synchronous entry point.

    Always compiles to PDF at the end.
    Run log written to ``execution_dir/editor_run.log`` and mirrored to stderr.
    Set ``verbose_log=False`` to suppress stderr output (log still written to disk).
    """
    settings = load_editor_settings(env_path)
    pipeline = EditorPipeline(settings)
    try:
        return asyncio.run(
            pipeline.run(
                execution_dir,
                ieee_format=ieee_format,
                verbose_log=verbose_log,
                resume=resume,
            )
        )
    except KeyboardInterrupt:
        pdf = execution_dir / "13_ieee_manuscript" / "main.pdf"
        if pdf.is_file():
            return EditorRunResult(
                pdf_path=str(pdf.resolve()),
                errors=["Editor interrupted during shutdown; PDF was already compiled."],
            )
        raise
