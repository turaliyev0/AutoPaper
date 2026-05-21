"""In-memory run registry with SSE pub/sub."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


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
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        for line in self.log_lines:
            q.put_nowait({"type": "log", "line": line})
        if self.status in (RunStatus.DONE, RunStatus.ERROR):
            q.put_nowait({"type": "done", "status": self.status.value})
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def push(self, event: dict[str, Any]) -> None:
        if event.get("type") == "log":
            self.log_lines.append(event["line"])
        elif event.get("type") == "step":
            self.current_step = event.get("message", "")
        for q in list(self._subscribers):
            q.put_nowait(event)

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


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, PipelineRun] = {}

    def create(self, *, paper_title: str, ieee_format: str) -> PipelineRun:
        run_id = uuid.uuid4().hex[:8]
        run = PipelineRun(
            run_id=run_id,
            paper_title=paper_title,
            ieee_format=ieee_format,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> PipelineRun | None:
        return self._runs.get(run_id)

    def delete(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def all(self) -> list[dict]:
        return [
            r.to_dict()
            for r in sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        ]


store = RunStore()
