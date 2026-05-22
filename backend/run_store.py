"""Run registry with disk persistence (survives API server reload)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RUNS_DIR = _PROJECT_ROOT / "output" / "_runs"


class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED  = "queued"
    RUNNING = "running"
    DONE    = "done"
    ERROR   = "error"


@dataclass
class PipelineRun:
    run_id: str
    paper_title: str
    ieee_format: str
    created_at: str
    status: RunStatus = RunStatus.PENDING
    execution_dir: str = ""
    pdf_path: str = ""
    log_lines: list[str] = field(default_factory=list)
    error: str = ""
    current_step: str = ""
    sections_ok: int = 0
    sections_total: int = 0
    validation_pass: int = 0
    validation_warn: int = 0
    validation_fail: int = 0
    _subscribers: list = field(default_factory=list, repr=False)

    def subscribe(self):
        import asyncio

        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        for line in self.log_lines:
            q.put_nowait({"type": "log", "line": line})
        if self.status in (RunStatus.DONE, RunStatus.ERROR):
            q.put_nowait({"type": "done", "status": self.status.value})
        return q

    def unsubscribe(self, q) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def push(self, event: dict[str, Any]) -> None:
        if event.get("type") == "log":
            line = event["line"]
            self.log_lines.append(line)
            _append_log_line(self.run_id, line)
        elif event.get("type") == "step":
            self.current_step = event.get("message", "")
        elif event.get("type") == "status":
            pass

        for q in list(self._subscribers):
            q.put_nowait(event)

        if event.get("type") in ("step", "status", "done"):
            _write_run_json(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "paper_title": self.paper_title,
            "ieee_format": self.ieee_format,
            "created_at": self.created_at,
            "status": self.status.value,
            "current_step": self.current_step,
            "execution_dir": self.execution_dir,
            "has_pdf": bool(self.pdf_path and Path(self.pdf_path).is_file()),
            "error": self.error,
            "sections_ok": self.sections_ok,
            "sections_total": self.sections_total,
            "validation_pass": self.validation_pass,
            "validation_warn": self.validation_warn,
            "validation_fail": self.validation_fail,
        }

    def to_persist_dict(self) -> dict[str, Any]:
        d = self.to_dict()
        d["pdf_path"] = self.pdf_path
        return d

    @classmethod
    def from_persist_dict(cls, data: dict[str, Any]) -> PipelineRun:
        status_raw = str(data.get("status", "pending"))
        try:
            status = RunStatus(status_raw)
        except ValueError:
            status = RunStatus.ERROR

        run = cls(
            run_id=str(data["run_id"]),
            paper_title=str(data.get("paper_title", "")),
            ieee_format=str(data.get("ieee_format", "journal")),
            created_at=str(data.get("created_at", "")),
            status=status,
            execution_dir=str(data.get("execution_dir", "")),
            pdf_path=str(data.get("pdf_path", "")),
            error=str(data.get("error", "")),
            current_step=str(data.get("current_step", "")),
            sections_ok=int(data.get("sections_ok", 0)),
            sections_total=int(data.get("sections_total", 0)),
            validation_pass=int(data.get("validation_pass", 0)),
            validation_warn=int(data.get("validation_warn", 0)),
            validation_fail=int(data.get("validation_fail", 0)),
        )
        run.log_lines = _read_log_lines(run.run_id)
        _reconcile_after_reload(run)
        return run


def _write_run_json(run: PipelineRun) -> None:
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _json_path(run.run_id).write_text(
        json.dumps(run.to_persist_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _json_path(run_id: str) -> Path:
    return _RUNS_DIR / f"{run_id}.json"


def _log_path(run_id: str) -> Path:
    return _RUNS_DIR / f"{run_id}.log"


def _append_log_line(run_id: str, line: str) -> None:
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with _log_path(run_id).open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _read_log_lines(run_id: str) -> list[str]:
    path = _log_path(run_id)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln]


def _reconcile_after_reload(run: PipelineRun) -> None:
    """Fix status when the server restarted while a subprocess was still running."""
    if run.status not in (RunStatus.RUNNING, RunStatus.QUEUED, RunStatus.PENDING):
        _resolve_pdf_on_disk(run)
        return

    _resolve_pdf_on_disk(run)
    if run.pdf_path and Path(run.pdf_path).is_file():
        run.status = RunStatus.DONE
        run.error = ""
        _write_run_json(run)
        return

    if run.status in (RunStatus.RUNNING, RunStatus.QUEUED):
        run.status = RunStatus.ERROR
        if not run.error:
            run.error = (
                "Server restarted during this run (e.g. uvicorn --reload). "
                "Check the execution folder on disk for partial outputs."
            )
        _append_log_line(
            run.run_id,
            f"[AutoPaper] Recovered run metadata; execution_dir={run.execution_dir}",
        )
        run.log_lines.append(
            f"[AutoPaper] Recovered run metadata; execution_dir={run.execution_dir}",
        )
    _write_run_json(run)


def _resolve_pdf_on_disk(run: PipelineRun) -> None:
    if run.pdf_path and Path(run.pdf_path).is_file():
        return
    if run.execution_dir:
        candidate = Path(run.execution_dir) / "13_ieee_manuscript" / "main.pdf"
        if candidate.is_file():
            run.pdf_path = str(candidate)


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, PipelineRun] = {}
        _RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all_from_disk()

    def _load_all_from_disk(self) -> None:
        for path in sorted(_RUNS_DIR.glob("*.json")):
            run_id = path.stem
            if run_id in self._runs:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._runs[run_id] = PipelineRun.from_persist_dict(data)
            except Exception as exc:
                logger.warning("Could not load run %s: %s", run_id, exc)

    def create(self, *, paper_title: str, ieee_format: str) -> PipelineRun:
        import uuid

        run_id = uuid.uuid4().hex[:8]
        run = PipelineRun(
            run_id=run_id,
            paper_title=paper_title,
            ieee_format=ieee_format,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._runs[run_id] = run
        log_file = _log_path(run_id)
        if log_file.is_file():
            log_file.unlink()
        self.persist(run)
        return run

    def persist(self, run: PipelineRun) -> None:
        _write_run_json(run)

    def get(self, run_id: str) -> PipelineRun | None:
        run = self._runs.get(run_id)
        if run is not None:
            return run
        path = _json_path(run_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            run = PipelineRun.from_persist_dict(data)
            self._runs[run_id] = run
            return run
        except Exception as exc:
            logger.warning("Could not load run %s on demand: %s", run_id, exc)
            return None

    def delete(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
        for path in (_json_path(run_id), _log_path(run_id)):
            if path.is_file():
                path.unlink()

    def all(self) -> list[dict]:
        self._load_all_from_disk()
        return [
            r.to_dict()
            for r in sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        ]

    def counts(self) -> dict[str, int]:
        self._load_all_from_disk()
        result: dict[str, int] = {}
        for r in self._runs.values():
            result[r.status.value] = result.get(r.status.value, 0) + 1
        return result


store = RunStore()
