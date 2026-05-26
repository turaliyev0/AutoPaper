from __future__ import annotations

from pathlib import Path

TEXT_GLOB_ORDER = ("*.md", "*.txt", "*.rst")
IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".tif",
    ".tiff",
}


def expected_subpaths() -> tuple[tuple[str, ...], ...]:
    return (
        ("description",),
        ("details",),
        ("images",),
        ("metadata",),
    )


def ensure_input_layout(root: Path) -> None:
    """Create description/, details/, images/, metadata/ under root if missing."""
    root.mkdir(parents=True, exist_ok=True)
    for parts in expected_subpaths():
        (root.joinpath(*parts)).mkdir(parents=True, exist_ok=True)


def verify_input_layout(root: Path) -> None:
    """Raise FileNotFoundError if any expected subdirectory is missing."""
    root = root.expanduser().resolve()
    for parts in expected_subpaths():
        p = root.joinpath(*parts)
        if not p.is_dir():
            raise FileNotFoundError(f"Missing directory: {p}")
