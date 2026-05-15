from pathlib import Path

from autopaper.inputs.layout import ensure_input_layout, expected_subpaths, verify_input_layout


def input_ensure_layout_creates_subdirs(tmp_path: Path) -> None:
    root = tmp_path / "input"
    ensure_input_layout(root)
    for parts in expected_subpaths():
        assert (root.joinpath(*parts)).is_dir()


def input_verify_layout_detects_missing(tmp_path: Path) -> None:
    root = tmp_path / "partial"
    root.mkdir()
    (root / "description").mkdir()
    try:
        verify_input_layout(root)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
