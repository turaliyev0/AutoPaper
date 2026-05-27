"""
Structured run log for the editor pipeline.

Writes a human-readable log to ``editor_run.log`` inside the execution
directory *and* echoes every line to stderr so you can watch it live.

Usage inside the pipeline::

    log = RunLog(execution_dir)
    with log.step("Editor Orchestrator", agent="Gemini gemini-2.5-flash"):
        plan = await orchestrator.create_plan(context)
        log.info(f"Plan: {len(plan.sections)} sections, {len(plan.figures)} figures")
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

LOG_FILENAME = "editor_run.log"
_SEP = "=" * 80
_TICK = "\u2713"  # ✓
_CROSS = "\u2717"  # ✗
_ARROW = "\u2192"  # →


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


class RunLog:
    """
    Writes structured pipeline logs to ``execution_dir/editor_run.log``
    and mirrors every line to stderr.
    """

    def __init__(self, execution_dir: Path, *, verbose: bool = True) -> None:
        self._path = execution_dir / LOG_FILENAME
        self._verbose = verbose
        self._step_index = 0
        self._total_steps = 8
        self._start_time = time.monotonic()
        self._fh = self._path.open("w", encoding="utf-8")
        self._closed = False
        self._start_iso = _now_iso()

    # ------------------------------------------------------------------
    # Core emit
    # ------------------------------------------------------------------

    def _emit(self, line: str) -> None:
        if self._closed:
            return
        self._fh.write(line + "\n")
        self._fh.flush()
        if self._verbose:
            print(line, file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def header(self, execution_dir: Path, ieee_format: str) -> None:
        elapsed = ""
        self._emit(_SEP)
        self._emit(f"AUTOPAPER EDITOR PIPELINE — {self._start_iso}")
        self._emit(f"  execution_dir : {execution_dir}")
        self._emit(f"  ieee_format   : {ieee_format}")
        self._emit(_SEP)

    def info(self, msg: str) -> None:
        self._emit(f"    {msg}")

    def ok(self, msg: str) -> None:
        self._emit(f"    {_TICK} {msg}")

    def warn(self, msg: str) -> None:
        self._emit(f"    ! {msg}")

    def fail(self, msg: str) -> None:
        self._emit(f"    {_CROSS} {msg}")

    def arrow(self, msg: str) -> None:
        self._emit(f"    {_ARROW} {msg}")

    # ------------------------------------------------------------------
    # Step context manager
    # ------------------------------------------------------------------

    @contextmanager
    def step(self, name: str, *, agent: str = "") -> Generator[None, None, None]:
        self._step_index += 1
        elapsed = time.monotonic() - self._start_time
        m, s = divmod(int(elapsed), 60)
        ts = f"{m:02d}:{s:02d}"
        agent_tag = f" ({agent})" if agent else ""
        self._emit(f"\n[{ts}] STEP {self._step_index}/{self._total_steps} — {name}{agent_tag}")

        step_start = time.monotonic()
        error: BaseException | None = None
        try:
            yield
        except Exception as exc:
            error = exc
            self._emit(f"    {_CROSS} STEP FAILED: {exc}")
            raise
        finally:
            dur = time.monotonic() - step_start
            if error is None:
                self._emit(f"    Duration: {_duration(dur)}")

    # ------------------------------------------------------------------
    # Section / figure helpers
    # ------------------------------------------------------------------

    def log_sections(self, sections: list) -> None:
        for d in sections:
            cites = len(d.citations_used) if hasattr(d, "citations_used") else 0
            figs = len(d.figures_referenced) if hasattr(d, "figures_referenced") else 0
            tag = _TICK if d.success else _CROSS
            extra = f"  err: {d.error[:60]}" if not d.success and d.error else ""
            fig_note = f"  figs: {figs}" if figs else ""
            self._emit(
                f"    {tag} {d.section_id:<22} {d.word_count:>4}w  "
                f"cites: {cites}{fig_note}{extra}"
            )

    def log_figures(self, figures: list, specs: dict) -> None:
        for f in figures:
            spec = specs.get(f.figure_id)
            reuse = spec.reuse_path if spec else ""
            if f.success:
                how = f"reused {reuse}" if reuse and not f.code_path else f"generated (attempt {f.retries + 1})"
                self._emit(f"    {_TICK} {f.figure_id:<30} {how}")
            else:
                err = (f.error or "")[:70]
                self._emit(f"    {_CROSS} {f.figure_id:<30} FAILED — {err}")

    def log_validation(self, results: list) -> None:
        for v in results:
            tag = _TICK if v.verdict == "pass" else ("!" if v.verdict == "warn" else _CROSS)
            issues_str = ""
            if v.issues:
                issues_str = f"  — {v.issues[0][:70]}"
            self._emit(f"    {tag} {v.section_id:<22} {v.verdict.upper()}{issues_str}")

    def log_plan(self, plan) -> None:
        self.ok(f"Title    : {plan.article_title}")
        self.ok(f"Format   : {plan.ieee_format}")
        self.ok(f"Sections : {len(plan.sections)}")
        self.ok(f"Figures  : {len(plan.figures)}")
        for s in plan.ordered_sections:
            slugs = f"  ({len(s.research_slugs)} slugs)" if s.research_slugs else ""
            self._emit(f"      [{s.order:02d}] {s.heading}{slugs}")

    def log_context(self, context) -> None:
        total = len(context.research_artifacts)
        trusted = len(context.trusted_artifacts)
        self.ok(f"Trusted research artifacts : {trusted}/{total}")
        self.ok(f"Citation pool              : {len(context.citation_pool)} sources")
        self.ok(f"Key claims                 : {len(context.manuscript.key_claims)}")
        self.ok(f"Images available           : {len(context.manuscript.usable_images())}")
        n_ex = len(context.manuscript.excluded_images)
        if n_ex:
            self.ok(f"Images excluded            : {n_ex}")
        self.ok(f"Mismatch flags             : {len(context.manuscript.mismatch_flags)}")
        if context.title:
            self.ok(f"Paper title                : {context.title}")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def footer(self, result) -> None:
        total = time.monotonic() - self._start_time
        ok_s = len(result.successful_sections)
        tot_s = len(result.sections)
        ok_f = len(result.successful_figures)
        tot_f = len(result.figures)
        v_pass = sum(1 for v in result.validation if v.verdict == "pass")
        v_warn = sum(1 for v in result.validation if v.verdict == "warn")
        v_fail = sum(1 for v in result.validation if v.verdict == "fail")

        self._emit(f"\n{_SEP}")
        self._emit(f"EDITOR RUN COMPLETE — {_now_iso()}")
        self._emit(f"  Total duration : {_duration(total)}")
        self._emit(f"  Sections       : {ok_s}/{tot_s} OK")
        self._emit(f"  Figures        : {ok_f}/{tot_f} OK")
        self._emit(f"  Validation     : {v_pass} pass / {v_warn} warn / {v_fail} fail")
        if result.pdf_path:
            from pathlib import Path as P
            p = P(result.pdf_path)
            if p.exists():
                kb = round(p.stat().st_size / 1024, 1)
                self._emit(f"  PDF            : {result.pdf_path} ({kb} KB)")
        if result.errors:
            self._emit(f"  Errors ({len(result.errors)}):")
            for e in result.errors:
                self._emit(f"    - {e[:100]}")
        self._emit(_SEP)
        self._closed = True
        self._fh.close()
        if self._verbose:
            print(f"\n[log] Full run log written to: {self._path}", file=sys.stderr, flush=True)
