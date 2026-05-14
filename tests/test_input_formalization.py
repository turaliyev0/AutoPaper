from pathlib import Path

from autopaper.pipeline.formalize_input import parse_model_json
from autopaper.pipeline.input_bundle import load_raw_input_bundle, truncate_bundle_for_llm
from autopaper.prompts.loader import build_input_formalization_run


def test_load_raw_input_bundle(tmp_path: Path) -> None:
    root = tmp_path / "in"
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


def test_truncate_bundle_for_llm_marks_long_files(tmp_path: Path) -> None:
    root = tmp_path / "in2"
    (root / "description").mkdir(parents=True)
    (root / "description" / "big.txt").write_text("x" * 100, encoding="utf-8")
    b = load_raw_input_bundle(root)
    t = truncate_bundle_for_llm(b, max_chars_per_file=20)
    assert t["description_files"][0]["content_was_truncated"] is True


def test_parse_model_json_fenced() -> None:
    raw = '```json\n{"pipeline_stage": "input_formalization", "x": true}\n```'
    d = parse_model_json(raw)
    assert d["pipeline_stage"] == "input_formalization" and d["x"] is True


def test_parse_model_json_plain() -> None:
    d = parse_model_json('  {"a": 2}  ')
    assert d == {"a": 2}


def test_build_input_formalization_run_with_custom_prompts(tmp_path: Path) -> None:
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
