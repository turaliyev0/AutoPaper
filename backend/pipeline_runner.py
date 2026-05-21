"""Runs the full AutoPaper pipeline as a subprocess and streams logs."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from backend.run_store import PipelineRun, RunStatus

_PROJECT_ROOT = Path(__file__).resolve().parents[1]   # AutoPaper/


async def run_pipeline(run: PipelineRun, input_path: Path, *, ieee_format: str = "journal") -> None:
    cmd = [
        sys.executable, "-m", "autopaper.main.app",
        "--input", str(input_path),
        "--full-research",
        "--ieee-edit",
        "--log-editor",
        "--force-continue-on-mismatch",
        "--ieee-format", ieee_format,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    # Strip color codes from subprocess output
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"

    run.status = RunStatus.RUNNING
    run.push({"type": "status", "status": "running"})
    run.push({"type": "log", "line": f"[AutoPaper] Starting pipeline for: {run.paper_title}"})
    run.push({"type": "log", "line": f"[AutoPaper] IEEE format: {ieee_format}"})
    run.push({"type": "log", "line": "[AutoPaper] ─" * 40})

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_PROJECT_ROOT),
            env=env,
        )

        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = _clean(raw.decode("utf-8", errors="replace").rstrip())
            if line:
                run.push({"type": "log", "line": line})
                _parse_progress(run, line)

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Pipeline exited with code {proc.returncode}")

        _resolve_pdf(run)
        run.status = RunStatus.DONE
        run.push({"type": "log", "line": "[AutoPaper] ✓ Pipeline completed successfully."})

    except Exception as exc:
        run.status = RunStatus.ERROR
        run.error = str(exc)
        run.push({"type": "log", "line": f"[AutoPaper] ERROR: {exc}"})

    run.push({"type": "done", "status": run.status.value})


# ── Helpers ──────────────────────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")
_UNICODE_BOX = str.maketrans({
    "\u2500": "-", "\u2502": "|", "\u2514": "+", "\u2510": "+",
    "\u250c": "+", "\u2518": "+", "\u252c": "+", "\u2524": "+",
    "\u251c": "+", "\u2534": "+", "\u253c": "+",
    "\u2713": "[OK]", "\u2717": "[FAIL]", "\u2714": "[OK]",
    "\u2192": "->", "\u2014": "--",
})

def _clean(line: str) -> str:
    line = _ANSI_RE.sub("", line)
    line = line.translate(_UNICODE_BOX)
    return line.strip()


_RUN_DIR_RE   = re.compile(r"Run directory:\s*(.+)")
_PDF_RE       = re.compile(r"PDF\s*:\s*(.+\.pdf)", re.IGNORECASE)
_SECTIONS_RE  = re.compile(r"Sections\s*:\s*(\d+)/(\d+)")
_VALID_RE     = re.compile(r"Validation.*?(\d+)\s*pass.*?(\d+)\s*warn.*?(\d+)\s*fail", re.IGNORECASE)
_EXEC_RE      = re.compile(r"execution_dir\s*:\s*(.+)")


def _parse_progress(run: PipelineRun, line: str) -> None:
    m = _RUN_DIR_RE.search(line)
    if m:
        run.execution_dir = m.group(1).strip()

    m = _EXEC_RE.search(line)
    if m and not run.execution_dir:
        run.execution_dir = m.group(1).strip()

    m = _PDF_RE.search(line)
    if m:
        run.pdf_path = m.group(1).strip()

    m = _SECTIONS_RE.search(line)
    if m:
        run.sections_ok = int(m.group(1))
        run.sections_total = int(m.group(2))

    m = _VALID_RE.search(line)
    if m:
        run.validation_pass = int(m.group(1))
        run.validation_warn = int(m.group(2))
        run.validation_fail = int(m.group(3))


def _resolve_pdf(run: PipelineRun) -> None:
    if run.pdf_path and Path(run.pdf_path).is_file():
        return
    if run.execution_dir:
        candidate = Path(run.execution_dir.strip()) / "13_ieee_manuscript" / "main.pdf"
        if candidate.is_file():
            run.pdf_path = str(candidate)
