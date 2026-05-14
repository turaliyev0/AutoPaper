from pathlib import Path

from autopaper.inputs.folder_loader import ensure_input_layout, load_input_folder


def test_ensure_and_load_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "my_input"
    ensure_input_layout(root)
    (root / "notes" / "a.md").write_text("# Lab\nWe tested X.", encoding="utf-8")
    (root / "prompts" / "main.txt").write_text("Focus on methodology.", encoding="utf-8")
    (root / "datasets" / "csv" / "m.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "images" / "fig1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "model_results" / "run.json").write_text('{"acc": 0.9}', encoding="utf-8")
    (root / "metadata" / "paper.json").write_text('{"title": "My Paper"}', encoding="utf-8")

    bundle = load_input_folder(root)
    ri = bundle.to_research_input("fallback")
    assert "Lab" in ri.notes
    assert ri.user_instructions == "Focus on methodology."
    assert "0.9" in ri.model_outputs or "acc" in ri.model_outputs
    assert "m.csv" in ri.technical_details
    assert "images/fig1.png" in ri.technical_details.replace("\\", "/")
    assert bundle.title == "My Paper"
    assert ri.extra_context.get("input_root")


def test_prompt_fallback(tmp_path: Path) -> None:
    root = tmp_path / "empty_prompts"
    ensure_input_layout(root)
    (root / "notes" / "n.txt").write_text("note", encoding="utf-8")
    bundle = load_input_folder(root)
    ri = bundle.to_research_input("USE_ME")
    assert ri.user_instructions == "USE_ME"
