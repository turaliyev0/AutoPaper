from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sanitize_input_folder_name(name: str) -> str:
    """Safe single-segment label from the input folder basename."""
    s = name.strip() or "input"
    s = re.sub(r"[^\w\-.]+", "_", s, flags=re.ASCII)
    s = re.sub(r"_+", "_", s).strip("_.").lower()
    if not s or s in {".", ".."}:
        return "input"
    return s[:120]


def allocate_run_directory(input_root: Path) -> Path:
    """
    Create ``<input_root>/output/run_<folder_name>_<n>/`` with the lowest ``n`` that does not yet exist.
    """
    input_root = input_root.expanduser().resolve()
    label = sanitize_input_folder_name(input_root.name)
    out = input_root / "output"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    while True:
        run_dir = out / f"run_{label}_{n}"
        try:
            run_dir.mkdir(exist_ok=False)
            return run_dir
        except FileExistsError:
            n += 1


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
