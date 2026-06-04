"""Figure agent — generates matplotlib Python code, executes it, validates output."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pipeline.research.clients.gemini_client import GeminiClient
from pipeline.research.utils import extract_json_object

from ..config import EditorSettings
from ..context import EditorContext
from ..prompts.loader import load_figure_generator_instruction
from ..schemas import FigureResult, FigureSpec

logger = logging.getLogger(__name__)

AGENT_ID = "figure_agent"


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


def _build_figure_prompt(
    spec: FigureSpec,
    output_path: str,
    context: EditorContext,
) -> str:
    import json

    save_path = output_path.replace("\\", "/")
    duration = context.manuscript.study_duration_weeks() or 12
    payload = {
        "figure_id": spec.figure_id,
        "caption": spec.caption,
        "intent": spec.intent,
        "data_hints": spec.data_hints,
        "output_path": save_path,
        "article_title": context.title,
        "key_claims": context.manuscript.key_claims[:8],
        "quantitative_evidence": context.manuscript.quantitative_outcome_lines()[:12],
        "study_duration_weeks": duration,
        "instructions": (
            "Generate ONLY a self-contained Python script using matplotlib. "
            "The script must save the figure to the exact path in 'output_path' and exit. "
            "On Windows use forward slashes in that path or assign it with a raw string (r'...'). "
            "Do NOT show a GUI window (use matplotlib.use('Agg') at the top). "
            "Use synthetic / illustrative data consistent with data_hints and quantitative_evidence. "
            f"For time-series plots, x-axis must run from week 0 through week {duration} only "
            f"(do not extend beyond the study duration). "
            "State SNR units explicitly in the y-axis label (ratio or dB) and match data_hints. "
            "Histology bar plots must include both flexible and rigid groups when the caption does. "
            "IEEE style: single-column width ~3.5in, 300 dpi, clean axis labels, no title on figure "
            "(caption handles it), legend if needed."
        ),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


async def _generate_code(
    client: GeminiClient,
    system: str,
    spec: FigureSpec,
    output_path: str,
    context: EditorContext,
    *,
    error_feedback: str = "",
) -> str:
    """Ask the LLM for Python matplotlib code. Returns the raw code string."""
    user = _build_figure_prompt(spec, output_path, context)
    if error_feedback:
        user += (
            f"\n\n--- PREVIOUS ATTEMPT FAILED ---\n{error_feedback}\n"
            "Fix the code based on the error above."
        )
    data = await client.generate_json(
        system=system,
        user=user,
        trace_label=f"figure_agent:{spec.figure_id}",
    )
    return _normalize_figure_code(str(data.get("code") or ""))


def _normalize_figure_code(raw: str) -> str:
    """Strip markdown fences if the model wrapped the script."""
    code = raw.strip()
    if not code.startswith("```"):
        return code
    lines = code.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Execution + validation
# ---------------------------------------------------------------------------


def _figure_subprocess_env(cwd: Path) -> dict[str, str]:
    """Minimal environment for matplotlib child (Windows-safe, no project PYTHONPATH)."""
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(cwd / ".mplconfig")
    # Inherit only what the interpreter needs; avoid pulling AutoPaper into the child.
    for key in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        env.pop(key, None)
    return env


def _subprocess_run_kwargs() -> dict[str, Any]:
    """Isolate figure child from parent Ctrl+C / asyncio cancellation (Windows)."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}  # type: ignore[attr-defined]
    return {"start_new_session": True}


def _execute_code(code: str, code_path: Path, timeout: int) -> tuple[bool, str]:
    """Run matplotlib in a temp script dir; persist .py under output only after the attempt."""
    code_path = code_path.resolve()
    figures_dir = code_path.parent
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Run outside the repo (never under output/) so uvicorn --reload does not restart the API.
    try:
        with tempfile.TemporaryDirectory(prefix="autopaper_fig_") as tmp:
            tmp_dir = Path(tmp)
            run_script = tmp_dir / "run_figure.py"
            run_script.write_text(code, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-u", str(run_script.resolve())],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(tmp_dir),
                env=_figure_subprocess_env(tmp_dir),
                **_subprocess_run_kwargs(),
            )
    except subprocess.TimeoutExpired:
        return False, (
            f"Execution timed out after {timeout}s "
            "(matplotlib cold start on Windows can take 30–60s)."
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode != 0:
        err = (result.stderr or result.stdout)[:1000]
        if "KeyboardInterrupt" in err:
            return (
                False,
                "Figure subprocess was interrupted (server reload or stop). "
                "Use `python run_dev.py` (reload_dirs excludes output/) or run without --reload.",
            )
        return False, err
    return True, ""


def _persist_figure_script(code: str, code_path: Path) -> None:
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text(code, encoding="utf-8")


def _validate_output(output_path: Path) -> tuple[bool, str]:
    """Fast technical validation: exists, readable, and non-trivial size."""
    if not output_path.exists():
        return False, f"Output file not found: {output_path}"
    size = output_path.stat().st_size
    if size < 1024:
        return False, f"Output file too small ({size} bytes); likely empty."
    try:
        with output_path.open("rb") as fh:
            header = fh.read(8)
        if output_path.suffix.lower() == ".png" and header != b"\x89PNG\r\n\x1a\n":
            return False, "Output exists but is not a valid PNG header."
    except Exception as exc:
        return False, f"Output exists but cannot be opened/read: {exc}"
    return True, ""


def _build_ai_validation_payload(
    spec: FigureSpec,
    *,
    output_path: Path,
    code: str,
) -> str:
    import json

    payload = {
        "figure_id": spec.figure_id,
        "caption": spec.caption,
        "intent": spec.intent,
        "data_hints": spec.data_hints,
        "output_path": str(output_path),
        "generated_code_preview": code[:2400],
        "task": (
            "Validate whether the generated figure implementation is consistent with caption/intent/data_hints. "
            "Use code semantics and metadata; do not invent details about unseen pixels."
        ),
        "output_schema": {
            "verdict": "pass|fail",
            "issues": ["string"],
            "feedback_for_retry": "string",
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


async def _ai_validate_figure(
    client: GeminiClient,
    spec: FigureSpec,
    *,
    output_path: Path,
    code: str,
) -> tuple[bool, str]:
    """LLM validation used only after technical checks pass."""
    system = (
        "You are a strict figure QA validator.\n"
        "Given caption/intent/data_hints and generated matplotlib code, decide consistency.\n"
        "Return JSON: {verdict:'pass|fail', issues:[...], feedback_for_retry:'...'}.\n"
        "Use fail when labels/metrics/plot type are mismatched or key hints are ignored."
    )
    user = _build_ai_validation_payload(spec, output_path=output_path, code=code)
    data = await client.generate_json(
        system=system,
        user=user,
        trace_label=f"figure_validator:{spec.figure_id}",
    )
    verdict = str(data.get("verdict") or "pass").strip().lower()
    issues = [str(i).strip() for i in (data.get("issues") or []) if str(i).strip()]
    retry_feedback = str(data.get("feedback_for_retry") or "").strip()
    if verdict == "fail":
        reason = "; ".join(issues) if issues else "AI validation failed."
        if retry_feedback:
            reason += f"\nRetry guidance: {retry_feedback}"
        return False, reason
    return True, ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class FigureAgent:
    """
    Generates a figure for one :class:`FigureSpec`.

    If ``spec.reuse_path`` is set and the file exists in the execution dir,
    it is copied to the figures dir without code generation.
    """

    def __init__(self, client: GeminiClient, settings: EditorSettings) -> None:
        self._client = client
        self._settings = settings
        self._system = load_figure_generator_instruction()

    async def generate(
        self,
        spec: FigureSpec,
        figures_dir: Path,
        context: EditorContext,
        *,
        qa_feedback: str = "",
    ) -> FigureResult:
        if spec.reuse_path and spec.reuse_path.strip() in context.manuscript.excluded_paths():
            logger.warning(
                "Figure %s: reuse_path '%s' is excluded; generating new figure instead.",
                spec.figure_id,
                spec.reuse_path,
            )
            spec = spec.model_copy(update={"reuse_path": ""})

        # --- reuse existing image if available ---
        if spec.reuse_path:
            # Search order: input_root (original paper folder), then execution_dir
            candidate_roots = []
            if context.input_root is not None:
                candidate_roots.append(context.input_root)
            candidate_roots.append(context.execution_dir)

            reused_src: Path | None = None
            for root in candidate_roots:
                candidate = root / spec.reuse_path
                if candidate.is_file():
                    reused_src = candidate
                    break

            if reused_src is not None:
                dst = figures_dir / f"{spec.figure_id}{reused_src.suffix}"
                shutil.copy2(reused_src, dst)
                logger.info("Figure %s: reused %s", spec.figure_id, reused_src)
                return FigureResult(
                    figure_id=spec.figure_id,
                    output_path=str(dst),
                    code_path="",
                    success=True,
                    retries=0,
                    validation_notes=f"Reused existing image from {reused_src}.",
                )
            else:
                logger.warning(
                    "Figure %s: reuse_path '%s' not found in input_root or execution_dir; generating new.",
                    spec.figure_id, spec.reuse_path,
                )

        # --- generate new figure ---
        output_path = figures_dir / f"{spec.figure_id}.png"
        code_path = figures_dir / f"{spec.figure_id}.py"
        # Hard safety cap: never loop more than 3 attempts for figure generation/validation.
        max_retries = min(self._settings.editor_figure_max_retries, 3)
        timeout = self._settings.editor_figure_exec_timeout

        error_feedback = qa_feedback.strip()
        code = ""
        for attempt in range(max_retries):
            logger.info("FigureAgent: generating %s (attempt %d)", spec.figure_id, attempt + 1)
            try:
                code = await _generate_code(
                    self._client,
                    self._system,
                    spec,
                    str(output_path),
                    context,
                    error_feedback=error_feedback,
                )
            except Exception as exc:
                logger.warning("Code generation failed: %s", exc)
                error_feedback = f"Code generation error: {exc}"
                continue

            if not code.strip():
                error_feedback = "LLM returned empty code."
                continue

            exec_ok, exec_err = await asyncio.to_thread(
                _execute_code, code, code_path, timeout
            )
            if not exec_ok:
                error_feedback = f"Execution error (attempt {attempt + 1}):\n{exec_err}"
                logger.warning("Figure %s execution failed: %s", spec.figure_id, exec_err)
                continue

            file_ok, file_err = _validate_output(output_path)
            if not file_ok:
                error_feedback = f"Output validation error (attempt {attempt + 1}):\n{file_err}"
                logger.warning("Figure %s output invalid: %s", spec.figure_id, file_err)
                continue

            # Stage 2 (AI validation): run only after cheap technical checks pass.
            try:
                ai_ok, ai_err = await _ai_validate_figure(
                    self._client,
                    spec,
                    output_path=output_path,
                    code=code,
                )
            except Exception as exc:
                # Do not fail the run on validator-side transient errors.
                logger.warning("Figure %s AI validation skipped due to error: %s", spec.figure_id, exc)
                ai_ok, ai_err = True, ""
            if not ai_ok:
                error_feedback = f"AI validation error (attempt {attempt + 1}):\n{ai_err}"
                logger.warning("Figure %s AI validation failed: %s", spec.figure_id, ai_err)
                continue

            _persist_figure_script(code, code_path)
            return FigureResult(
                figure_id=spec.figure_id,
                output_path=str(output_path),
                code_path=str(code_path),
                success=True,
                retries=attempt,
                validation_notes=f"Generated on attempt {attempt + 1}.",
            )

        if error_feedback and code.strip():
            _persist_figure_script(code, code_path)

        return FigureResult(
            figure_id=spec.figure_id,
            output_path="",
            code_path=str(code_path) if code_path.exists() else "",
            success=False,
            retries=max_retries,
            error=error_feedback or f"Failed after {max_retries} attempts.",
        )
