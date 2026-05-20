"""Layout verification and disk-only raw bundle ingest (no LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_input.ingest import load_raw_input_bundle
from paper_input.layout import (
    IMAGE_SUFFIXES,
    ensure_input_layout,
    expected_subpaths,
    verify_input_layout,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def sample_root() -> Path:
    return REPO_ROOT / "examples" / "sample_paper_input"


@pytest.fixture
def neuro_root() -> Path:
    return REPO_ROOT / "examples" / "neuro_stability"


def test_expected_subpaths_covers_standard_layout() -> None:
    names = {parts[0] for parts in expected_subpaths()}
    assert names == {"description", "details", "images", "metadata"}


def test_verify_input_layout_sample_paper_input(sample_root: Path) -> None:
    verify_input_layout(sample_root)


def test_verify_input_layout_neuro_stability(neuro_root: Path) -> None:
    verify_input_layout(neuro_root)


def test_ensure_input_layout_creates_dirs(tmp_path: Path) -> None:
    root = tmp_path / "empty_project"
    ensure_input_layout(root)
    verify_input_layout(root)


def test_load_raw_input_bundle_sample(sample_root: Path) -> None:
    bundle = load_raw_input_bundle(sample_root)
    assert Path(bundle["input_root"]) == sample_root.resolve()
    assert isinstance(bundle.get("description_files"), list)
    assert isinstance(bundle.get("details_files"), list)
    assert isinstance(bundle.get("metadata_json_files"), list)
    assert isinstance(bundle.get("image_paths"), list)
    # sample has at least description content
    desc = bundle["description_files"]
    assert any("description" in str(d.get("relative_path", "")) for d in desc)


def test_load_raw_input_bundle_neuro_has_images(neuro_root: Path) -> None:
    bundle = load_raw_input_bundle(neuro_root)
    paths = bundle["image_paths"]
    assert paths, "neuro_stability should list images/"
    for rel in paths:
        assert rel.startswith("images/")
        assert Path(rel).suffix.lower() in IMAGE_SUFFIXES
    p = neuro_root / paths[0]
    assert p.is_file()


def test_load_raw_input_bundle_metadata_json_parsed(sample_root: Path) -> None:
    bundle = load_raw_input_bundle(sample_root)
    meta = bundle.get("metadata_json_files") or []
    assert meta, "sample_paper_input should have metadata/*.json"
    first = meta[0]
    assert "parsed" in first
    assert "_parse_error" not in first.get("parsed", {})


def test_cli_help_parses_without_tty() -> None:
    """Smoke: argparse does not require --input when only --help is used."""
    from autopaper.main import app

    with pytest.raises(SystemExit) as exc:
        app.main(["--help"])
    assert exc.value.code == 0
