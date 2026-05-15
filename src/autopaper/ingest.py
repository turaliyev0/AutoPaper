from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autopaper.inputs.bundle import load_raw_input_bundle
from autopaper.inputs.layout import ensure_input_layout, verify_input_layout
from autopaper.run_directory import allocate_run_directory, write_run_manifest


def prepare_input_run(
    root: Path,
    *,
    run_dir: Path | None = None,
    create_layout: bool = True,
) -> tuple[dict[str, Any], Path]:
    """
    Load the input folder into a bundle JSON and create ``output/run_<name>_<n>/``
    with ``01_raw_input_bundle.json`` and ``00_run_manifest.json``.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    if create_layout:
        ensure_input_layout(root)
    else:
        verify_input_layout(root)

    bundle = load_raw_input_bundle(root)
    run_path = run_dir if run_dir is not None else allocate_run_directory(root)
    run_path.mkdir(parents=True, exist_ok=True)

    (run_path / "01_raw_input_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_run_manifest(
        run_path,
        pipeline="input_ingest",
        input_root=root,
        extra={"steps": ["00_run_manifest.json", "01_raw_input_bundle.json"]},
    )
    return bundle, run_path
