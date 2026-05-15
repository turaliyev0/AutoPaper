from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_EXECUTION_DIR_PATTERN = re.compile(r"^execution_(\d+)$", re.IGNORECASE)


def allocate_execution_directory(input_root: Path) -> Path:
    """
    Create ``<input_root>/output/execution_NNN/`` where ``NNN`` is zero-padded
    (``execution_001``, ``execution_002``, …): one greater than the highest
    existing ``execution_<number>`` directory under ``output/``.
    """
    input_root = input_root.expanduser().resolve()
    out = input_root / "output"
    out.mkdir(parents=True, exist_ok=True)
    max_num = 0
    for p in out.iterdir():
        if not p.is_dir():
            continue
        m = _EXECUTION_DIR_PATTERN.match(p.name)
        if m:
            max_num = max(max_num, int(m.group(1)))
    next_num = max_num + 1
    while True:
        name = f"execution_{next_num:03d}"
        run_dir = out / name
        try:
            run_dir.mkdir(exist_ok=False)
            return run_dir
        except FileExistsError:
            next_num += 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_run_manifest(
    run_dir: Path,
    *,
    pipeline: str,
    input_root: Path,
    extra: dict | None = None,
) -> None:
    body = {
        "pipeline": pipeline,
        "input_root": str(input_root.resolve()),
        "run_directory": str(run_dir.resolve()),
        "created_at_utc": utc_now_iso(),
    }
    if extra:
        body.update(extra)
    (run_dir / "00_run_manifest.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_run_manifest_steps(run_dir: Path, *additional_steps: str) -> None:
    """Append unique step filenames to ``steps`` in ``00_run_manifest.json`` if present."""
    path = run_dir / "00_run_manifest.json"
    if not path.is_file():
        return
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    steps = list(data.get("steps", []))
    for s in additional_steps:
        if s not in steps:
            steps.append(s)
    data["steps"] = steps
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
