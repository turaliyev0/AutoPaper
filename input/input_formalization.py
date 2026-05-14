import json
from pathlib import Path

from autopaper.pipeline.formalize_input import parse_model_json, run_input_formalization
from autopaper.pipeline.input_bundle import load_raw_input_bundle, truncate_bundle_for_llm
from autopaper.prompts.loader import build_input_formalization_run


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


def input_truncation_marks_long_files(tmp_path: Path) -> None:
    root = tmp_path / "input_truncation"
    (root / "description").mkdir(parents=True)
    (root / "description" / "big.txt").write_text("x" * 100, encoding="utf-8")
    b = load_raw_input_bundle(root)
    t = truncate_bundle_for_llm(b, max_chars_per_file=20)
    assert t["description_files"][0]["content_was_truncated"] is True


def input_parse_model_json_fenced() -> None:
    raw = '```json\n{"pipeline_stage": "input_formalization", "x": true}\n```'
    d = parse_model_json(raw)
    assert d["pipeline_stage"] == "input_formalization" and d["x"] is True


def input_parse_model_json_plain() -> None:
    d = parse_model_json('  {"a": 2}  ')
    assert d == {"a": 2}


def input_build_consolidated_structure() -> None:
    from autopaper.pipeline.consolidated_input import build_consolidated_input

    raw = {"input_root": "/x", "image_paths": ["images/a.png"]}
    doc = build_consolidated_input(
        raw_bundle=raw,
        truncated_bundle={},
        formalization_run={"messages": []},
        image_records=[{"relative_path": "images/a.png", "ai_description": "chart"}],
    )
    assert doc["raw_input_bundle"] == raw
    assert doc["images"][0]["ai_description"] == "chart"


def input_formalization_prompts_custom_tree(tmp_path: Path) -> None:
    p = tmp_path / "prompts"
    (p / "input_formalization").mkdir(parents=True)
    (p / "manifest.json").write_text(
        '{"input_formalization": {"system": "input_formalization/system_v1.md", '
        '"user": "input_formalization/user_v1.md"}}',
        encoding="utf-8",
    )
    (p / "assistants.json").write_text('{"input_formalization": {}}', encoding="utf-8")
    (p / "input_formalization" / "system_v1.md").write_text("SYS", encoding="utf-8")
    (p / "input_formalization" / "user_v1.md").write_text(
        "U\n{{RAW_INPUT_BUNDLE_JSON}}", encoding="utf-8"
    )

    run = build_input_formalization_run({"k": 1}, prompts_dir=p)
    assert run["messages"][0]["content"] == "SYS"
    assert '"k": 1' in run["messages"][1]["content"]
    assert run["prompt_files"]["system"] == "input_formalization/system_v1.md"


def input_formalization_run_numbered_artifacts(tmp_path: Path) -> None:
    p = tmp_path / "prompts"
    (p / "input_formalization").mkdir(parents=True)
    (p / "manifest.json").write_text(
        '{"input_formalization": {"system": "input_formalization/system_v1.md", '
        '"user": "input_formalization/user_v1.md"}}',
        encoding="utf-8",
    )
    (p / "assistants.json").write_text("{}", encoding="utf-8")
    (p / "input_formalization" / "system_v1.md").write_text("S", encoding="utf-8")
    (p / "input_formalization" / "user_v1.md").write_text("{{RAW_INPUT_BUNDLE_JSON}}", encoding="utf-8")

    root = tmp_path / "input"
    (root / "description").mkdir(parents=True)
    (root / "description" / "n.txt").write_text("x", encoding="utf-8")
    (root / "details").mkdir(parents=True)
    (root / "images").mkdir(parents=True)
    (root / "images" / "fig1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "metadata").mkdir(parents=True)

    _, run_dir = run_input_formalization(root, save_raw=True, prompts_dir=p)
    assert run_dir.name.startswith("run_input_")
    assert (run_dir / "00_run_manifest.json").is_file()
    assert (run_dir / "01_raw_input_bundle.json").is_file()
    assert (run_dir / "02_truncated_bundle_for_llm.json").is_file()
    assert (run_dir / "03_assembled_prompts.json").is_file()
    assert (run_dir / "04_model_response.json").is_file()
    assert (run_dir / "05_consolidated_input.json").is_file()
    data = json.loads((run_dir / "05_consolidated_input.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "images" in data and len(data["images"]) >= 1
    assert data["images"][0]["relative_path"] == "images/fig1.png"
