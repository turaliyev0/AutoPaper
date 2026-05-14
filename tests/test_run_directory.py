from pathlib import Path

from autopaper.pipeline.run_directory import allocate_run_directory, sanitize_input_folder_name


def test_sanitize_input_folder_name() -> None:
    assert sanitize_input_folder_name("My Data!") == "my_data"
    assert sanitize_input_folder_name("") == "input"


def test_allocate_run_directory_increments(tmp_path: Path) -> None:
    root = tmp_path / "MyCase"
    root.mkdir()
    r0 = allocate_run_directory(root)
    assert r0.name == "run_mycase_0"
    r1 = allocate_run_directory(root)
    assert r1.name == "run_mycase_1"
    assert (r0 / "x").write_text("a", encoding="utf-8") or True
    assert r0.is_dir() and r1.is_dir()
