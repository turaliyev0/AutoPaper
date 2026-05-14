from pathlib import Path

from autopaper.inputs.folder_loader import ensure_input_layout, load_input_folder


def input_ensure_layout_load_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "input"
    ensure_input_layout(root)
    (root / "description" / "a.md").write_text("# Lab\nWe tested X.", encoding="utf-8")
    (root / "details" / "main.txt").write_text("Focus on methodology.", encoding="utf-8")
    (root / "images" / "fig1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "metadata" / "paper.json").write_text('{"title": "My Paper"}', encoding="utf-8")

    bundle = load_input_folder(root)
    ri = bundle.to_research_input("fallback")
    assert "Lab" in ri.description
    assert ri.details == "Focus on methodology."
    assert "fig1.png" in ri.technical_details.replace("\\", "/")
    assert bundle.title == "My Paper"
    assert ri.extra_context.get("input_root")


def input_details_fallback(tmp_path: Path) -> None:
    root = tmp_path / "input_no_details"
    ensure_input_layout(root)
    (root / "description" / "n.txt").write_text("note", encoding="utf-8")
    bundle = load_input_folder(root)
    ri = bundle.to_research_input("USE_ME")
    assert ri.details == "USE_ME"
