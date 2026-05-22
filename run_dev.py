"""Dev server: hot-reload API without restarting when the pipeline writes under output/."""

from __future__ import annotations

from pathlib import Path

import uvicorn

# Watch only application source trees (relative to repo root).
_RELOAD_DIRS = [
    "backend",
    "src",
    "editor",
    "research",
    "paper_input",
]

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    output_dir = root / "output"

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=_RELOAD_DIRS,
        reload_includes=[f"{d}/**/*.py" for d in _RELOAD_DIRS],
        reload_excludes=[
            str(output_dir),
            "output",
            "output/**",
            "**/output/**",
            "frontend/**",
        ],
    )
