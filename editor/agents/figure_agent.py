"""Figure agent — generates matplotlib Python code, executes it, validates output."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from research.clients.openai_client import OpenAIClient
from research.utils import extract_json_object

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

    payload = {
        "figure_id": spec.figure_id,
        "caption": spec.caption,
        "intent": spec.intent,
        "data_hints": spec.data_hints,
        "output_path": output_path,
        "article_title": context.title,
        "key_claims": context.manuscript.key_claims[:8],
        "instructions": (
            "Generate ONLY a self-contained Python script using matplotlib. "
            "The script must save the figure to the exact path in 'output_path' and exit. "
            "Do NOT show a GUI window (use matplotlib.use('Agg') at the top). "
            "Use synthetic / illustrative data consistent with data_hints if real data is unavailable. "
            "IEEE style: single-column width ~3.5in, 300 dpi, clean axis labels, no title on figure "
            "(caption handles it), legend if needed."
        ),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


async def _generate_code(
    client: OpenAIClient,
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
    return str(data.get("code") or "")


# ---------------------------------------------------------------------------
# Execution + validation
# ---------------------------------------------------------------------------


def _execute_code(code: str, code_path: Path, timeout: int) -> tuple[bool, str]:
    """Write code to disk and run it. Returns (success, stderr)."""
    code_path.write_text(code, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(code_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout)[:1000]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"Execution timed out after {timeout}s."
    except Exception as exc:
        return False, str(exc)


def _validate_output(output_path: Path) -> tuple[bool, str]:
    """Check that the figure file was created and is non-empty."""
    if not output_path.exists():
        return False, f"Output file not found: {output_path}"
    if output_path.stat().st_size < 1024:
        return False, f"Output file too small ({output_path.stat().st_size} bytes); likely empty."
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

    def __init__(self, client: OpenAIClient, settings: EditorSettings) -> None:
        self._client = client
        self._settings = settings
        self._system = load_figure_generator_instruction()

    async def generate(
        self,
        spec: FigureSpec,
        figures_dir: Path,
        context: EditorContext,
    ) -> FigureResult:
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
        max_retries = self._settings.editor_figure_max_retries
        timeout = self._settings.editor_figure_exec_timeout

        error_feedback = ""
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

            exec_ok, exec_err = _execute_code(code, code_path, timeout)
            if not exec_ok:
                error_feedback = f"Execution error (attempt {attempt + 1}):\n{exec_err}"
                logger.warning("Figure %s execution failed: %s", spec.figure_id, exec_err)
                continue

            file_ok, file_err = _validate_output(output_path)
            if not file_ok:
                error_feedback = f"Output validation error (attempt {attempt + 1}):\n{file_err}"
                logger.warning("Figure %s output invalid: %s", spec.figure_id, file_err)
                continue

            return FigureResult(
                figure_id=spec.figure_id,
                output_path=str(output_path),
                code_path=str(code_path),
                success=True,
                retries=attempt,
                validation_notes=f"Generated on attempt {attempt + 1}.",
            )

        return FigureResult(
            figure_id=spec.figure_id,
            output_path="",
            code_path=str(code_path) if code_path.exists() else "",
            success=False,
            retries=max_retries,
            error=error_feedback or f"Failed after {max_retries} attempts.",
        )
