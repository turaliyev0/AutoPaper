import json
from pathlib import Path

from autopaper.inputs.bundle import load_raw_input_bundle


def input_load_raw_input_bundle(tmp_path: Path) -> None:
    root = tmp_path / "input"
    (root / "description").mkdir(parents=True)
    (root / "details").mkdir(parents=True)
    (root / "images").mkdir(parents=True)
    (root / "metadata").mkdir(parents=True)
    (root / "description" / "a.txt").write_text("hello", encoding="utf-8")
    (root / "details" / "b.md").write_text("# Req", encoding="utf-8")
    (root / "metadata" / "paper.json").write_text('{"title": "T"}', encoding="utf-8")
    (root / "images" / "f.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    b = load_raw_input_bundle(root)
    assert b["input_root"] == root.resolve().as_posix()
    assert len(b["description_files"]) == 1
    assert b["description_files"][0]["relative_path"] == "description/a.txt"
    assert b["image_paths"] == ["images/f.png"]
    assert b["metadata_json_files"][0]["parsed"]["title"] == "T"


def input_ingest_writes_run_artifacts(tmp_path: Path) -> None:
    from autopaper.ingest import prepare_input_run

    root = tmp_path / "input"
    (root / "description").mkdir(parents=True)
    (root / "details").mkdir(parents=True)
    (root / "images").mkdir(parents=True)
    (root / "metadata").mkdir(parents=True)
    (root / "description" / "n.txt").write_text("x", encoding="utf-8")

    _, run_dir = prepare_input_run(root, create_layout=False)
    assert run_dir.name.startswith("run_input_")
    assert (run_dir / "00_run_manifest.json").is_file()
    assert (run_dir / "01_raw_input_bundle.json").is_file()
    data = json.loads((run_dir / "01_raw_input_bundle.json").read_text(encoding="utf-8"))
    assert data["input_root"] == root.resolve().as_posix()
