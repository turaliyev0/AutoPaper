"""Run the full AutoPaper pipeline as a subprocess and stream logs."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from backend.db.run_store import PipelineRun, RunStatus, store

from .config import PipelineRunConfig
from .provider_log import provider_status_lines, sanitize_subprocess_env, should_hide_user_log_line

INPUT_GAPS_EXIT_CODE = 3

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

MAX_CONCURRENT_RUNS: int = int(os.environ.get("AUTOPAPER_MAX_CONCURRENT_RUNS", "2"))
_semaphore: asyncio.Semaphore | None = None

_INTERRUPT_EXIT_CODES = frozenset({130, -2, -1073741510, 3221225786})


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
    return _semaphore


async def run_pipeline(
    run: PipelineRun,
    input_path: Path,
    *,
    ieee_format: str = "journal",
    config: PipelineRunConfig | None = None,
) -> None:
    sem = _get_semaphore()

    if sem.locked():
        run.status = RunStatus.QUEUED
        run.push({"type": "status", "status": "queued"})
        run.push({
            "type": "log",
            "line": (
                f"[AutoPaper] Run queued — {MAX_CONCURRENT_RUNS} pipeline(s) already running. "
                "Will start automatically when a slot opens."
            ),
        })

    async with sem:
        await _execute(run, input_path, ieee_format=ieee_format, config=config or PipelineRunConfig())


def _build_cmd(input_path: Path, ieee_format: str, config: PipelineRunConfig) -> list[str]:
    cmd = [
        sys.executable, "-m", "autopaper.main.app",
        "--input", str(input_path),
        "--ieee-format", ieee_format,
    ]
    if config.ingest_only:
        cmd.append("--no-research")
    elif config.full_research:
        cmd.append("--full-research")
    if config.ieee_edit and not config.ingest_only:
        cmd.append("--ieee-edit")
        if config.log_editor:
            cmd.append("--log-editor")
    if config.mismatch_policy == "strict":
        cmd.append("--strict")
    else:
        cmd.append("--force-continue-on-mismatch")
    if config.completeness_policy == "strict":
        cmd.append("--strict-input-gaps")
    elif config.completeness_policy == "continue":
        cmd.append("--force-continue-on-input-gaps")
    return cmd


def _build_continue_cmd(
    input_path: Path,
    execution_dir: Path,
    ieee_format: str,
    config: PipelineRunConfig,
) -> list[str]:
    cmd = [
        sys.executable, "-m", "autopaper.main.app",
        "--input", str(input_path),
        "--execution-dir", str(execution_dir),
        "--continue-after-gaps",
        "--ieee-format", ieee_format,
    ]
    if config.ingest_only:
        cmd.append("--no-research")
    elif config.full_research:
        cmd.append("--full-research")
    if config.ieee_edit and not config.ingest_only:
        cmd.append("--ieee-edit")
        if config.log_editor:
            cmd.append("--log-editor")
    return cmd


async def _execute(
    run: PipelineRun,
    input_path: Path,
    *,
    ieee_format: str,
    config: PipelineRunConfig,
) -> None:
    cmd = _build_cmd(input_path, ieee_format, config)

    env = sanitize_subprocess_env(os.environ.copy())
    env["PYTHONPATH"] = str(_PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["AUTOPAPER_QUIET_STARTUP"] = "1"
    env["AUTOPAPER_NON_INTERACTIVE"] = "1"

    run.status = RunStatus.RUNNING
    run.push({"type": "status", "status": "running"})
    run.push({"type": "log", "line": f"[AutoPaper] Starting pipeline for: {run.paper_title}"})
    run.push({"type": "log", "line": f"[AutoPaper] IEEE format: {ieee_format}"})
    for line in provider_status_lines():
        run.push({"type": "log", "line": line})
    run.push({"type": "log", "line": "[AutoPaper] " + "-" * 60})

    try:
        returncode = await _run_subprocess(cmd, env, str(_PROJECT_ROOT), run)
        _resolve_pdf(run)

        if returncode != 0:
            if returncode == INPUT_GAPS_EXIT_CODE:
                run.status = RunStatus.AWAITING_INPUT
                run.push({
                    "type": "log",
                    "line": (
                        "[AutoPaper] Input incomplete — waiting for user supplements. "
                        "Submit answers via POST /api/runs/{id}/supplement then pipeline continues."
                    ),
                })
                run.push({"type": "status", "status": "awaiting_input"})
                run.push({"type": "done", "status": "awaiting_input"})
                store.persist(run)
                return
            if _pdf_produced(run) and _is_interrupt_exit(returncode):
                run.push({
                    "type": "log",
                    "line": (
                        "[AutoPaper] Process was interrupted (e.g. server reload or Ctrl+C) "
                        "but the PDF was produced — run marked as done."
                    ),
                })
            else:
                raise RuntimeError(f"Pipeline exited with code {returncode}")

        run.status = RunStatus.DONE
        run.push({"type": "log", "line": "[AutoPaper] Pipeline completed successfully."})

    except Exception as exc:
        tb = traceback.format_exc()
        msg = repr(exc) if not str(exc) else str(exc)
        run.status = RunStatus.ERROR
        run.error = msg
        run.push({"type": "log", "line": f"[AutoPaper] ERROR: {msg}"})
        for tb_line in tb.splitlines():
            run.push({"type": "log", "line": f"  {tb_line}"})

    run.push({"type": "done", "status": run.status.value})
    store.persist(run)


def _handle_output_line(run: PipelineRun, raw: bytes) -> None:
    line = _clean(raw.decode("utf-8", errors="replace").rstrip())
    if not line or should_hide_user_log_line(line):
        return
    if line.startswith("[STEP]"):
        msg = line[6:].strip()
        run.push({"type": "step", "message": msg})
        run.push({"type": "log", "line": f"[Step] {msg}"})
    elif line.startswith("Run directory:"):
        run.push({"type": "log", "line": f"[AutoPaper] Output folder: {line.split(':', 1)[1].strip()}"})
        _parse_progress(run, line)
    else:
        run.push({"type": "log", "line": line})
        _parse_progress(run, line)


async def _run_subprocess(cmd: list[str], env: dict[str, str], cwd: str, run: PipelineRun) -> int:
    if sys.platform == "win32":
        return await _run_subprocess_threaded(cmd, env, cwd, run)
    return await _run_subprocess_asyncio(cmd, env, cwd, run)


def _detached_subprocess_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}  # type: ignore[attr-defined]
    return {"start_new_session": True}


async def _run_subprocess_asyncio(cmd: list[str], env: dict[str, str], cwd: str, run: PipelineRun) -> int:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
            **_detached_subprocess_kwargs(),
        )
    except NotImplementedError:
        return await _run_subprocess_threaded(cmd, env, cwd, run)

    if proc.stdout is None:
        raise RuntimeError("subprocess stdout pipe is None")
    async for raw in proc.stdout:
        _handle_output_line(run, raw)
    return await proc.wait() or 0


async def _run_subprocess_threaded(cmd: list[str], env: dict[str, str], cwd: str, run: PipelineRun) -> int:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    def worker() -> None:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=env,
                **_detached_subprocess_kwargs(),
            )
            if proc.stdout:
                for raw in proc.stdout:
                    loop.call_soon_threadsafe(queue.put_nowait, ("line", raw))
            code = proc.wait()
            loop.call_soon_threadsafe(queue.put_nowait, ("done", code))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        kind, payload = await queue.get()
        if kind == "line":
            _handle_output_line(run, payload)  # type: ignore[arg-type]
        elif kind == "done":
            return int(payload)
        elif kind == "error":
            raise payload  # type: ignore[misc]


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


_RUN_DIR_RE = re.compile(r"Run directory:\s*(.+)")
_PDF_RE = re.compile(r"PDF\s*:\s*(.+\.pdf)", re.IGNORECASE)
_SECTIONS_RE = re.compile(r"Sections\s*:\s*(\d+)/(\d+)")
_VALID_RE = re.compile(r"Validation.*?(\d+)\s*pass.*?(\d+)\s*warn.*?(\d+)\s*fail", re.IGNORECASE)
_EXEC_RE = re.compile(r"execution_dir\s*:\s*(.+)")


def _parse_progress(run: PipelineRun, line: str) -> None:
    prev_exec = run.execution_dir

    m = _RUN_DIR_RE.search(line)
    if m:
        run.execution_dir = m.group(1).strip()

    m = _EXEC_RE.search(line)
    if m and not run.execution_dir:
        run.execution_dir = m.group(1).strip()

    if run.execution_dir and run.execution_dir != prev_exec:
        store.persist(run)

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


def _is_interrupt_exit(code: int) -> bool:
    if code in _INTERRUPT_EXIT_CODES:
        return True
    if code >= 2**31:
        return (code - 2**32) in _INTERRUPT_EXIT_CODES
    return False


def _pdf_produced(run: PipelineRun) -> bool:
    return bool(run.pdf_path and Path(run.pdf_path).is_file())


def _resolve_pdf(run: PipelineRun) -> None:
    if _pdf_produced(run):
        return
    if run.execution_dir:
        candidate = Path(run.execution_dir.strip()) / "13_ieee_manuscript" / "main.pdf"
        if candidate.is_file():
            run.pdf_path = str(candidate)
            return
    for line in reversed(run.log_lines):
        m = _PDF_RE.search(line)
        if m:
            candidate = Path(m.group(1).strip())
            if candidate.is_file():
                run.pdf_path = str(candidate)
                return


async def run_pipeline_continue(
    run: PipelineRun,
    input_path: Path,
    execution_dir: Path,
    *,
    ieee_format: str = "journal",
    config: PipelineRunConfig | None = None,
    supplement_json: Path | None = None,
) -> None:
    """Resume after user submitted input supplements (research + optional editor)."""
    sem = _get_semaphore()
    async with sem:
        await _execute_continue(
            run,
            input_path,
            execution_dir,
            ieee_format=ieee_format,
            config=config or PipelineRunConfig(),
            supplement_json=supplement_json,
        )


async def _execute_continue(
    run: PipelineRun,
    input_path: Path,
    execution_dir: Path,
    *,
    ieee_format: str,
    config: PipelineRunConfig,
    supplement_json: Path | None = None,
) -> None:
    cmd = _build_continue_cmd(input_path, execution_dir, ieee_format, config)
    if supplement_json is not None:
        cmd.extend(["--supplement-json", str(supplement_json)])

    env = sanitize_subprocess_env(os.environ.copy())
    env["PYTHONPATH"] = str(_PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["AUTOPAPER_QUIET_STARTUP"] = "1"
    env["AUTOPAPER_NON_INTERACTIVE"] = "1"

    run.status = RunStatus.RUNNING
    run.execution_dir = str(execution_dir)
    run.push({"type": "status", "status": "running"})
    run.push({"type": "log", "line": "[AutoPaper] Resuming after user supplements…"})
    for line in provider_status_lines():
        run.push({"type": "log", "line": line})
    run.push({"type": "log", "line": "[AutoPaper] " + "-" * 60})

    try:
        returncode = await _run_subprocess(cmd, env, str(_PROJECT_ROOT), run)
        _resolve_pdf(run)
        if returncode != 0:
            raise RuntimeError(f"Pipeline resume exited with code {returncode}")
        run.status = RunStatus.DONE
        run.push({"type": "log", "line": "[AutoPaper] Pipeline completed successfully."})
    except Exception as exc:
        tb = traceback.format_exc()
        msg = repr(exc) if not str(exc) else str(exc)
        run.status = RunStatus.ERROR
        run.error = msg
        run.push({"type": "log", "line": f"[AutoPaper] ERROR: {msg}"})
        for tb_line in tb.splitlines():
            run.push({"type": "log", "line": f"  {tb_line}"})

    run.push({"type": "done", "status": run.status.value})
    store.persist(run)
