"""Per-agent environment variable names for ``paper_input`` Gemini agents."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

_dotenv_loaded = False


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[1]


def _load_repo_dotenv() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    env_file = _repo_root() / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class PaperInputAgent(str, Enum):
    TEXT_PARSER = "TEXT_PARSER"
    VISION = "VISION"
    JOINER = "JOINER"


def api_key_var(agent: PaperInputAgent) -> str:
    return f"PAPER_INPUT_{agent.value}_API_KEY"


def model_var(agent: PaperInputAgent) -> str:
    return f"PAPER_INPUT_{agent.value}_MODEL"


def resolve_api_key(
    agent: PaperInputAgent,
    *,
    override: str | None = None,
) -> str:
    _load_repo_dotenv()
    if override and override.strip():
        return override.strip()
    specific = os.environ.get(api_key_var(agent), "").strip()
    if specific:
        return specific
    for legacy in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        value = os.environ.get(legacy, "").strip()
        if value:
            return value
    raise RuntimeError(
        f"Missing API key for {agent.value}: set {api_key_var(agent)} "
        f"(or GOOGLE_API_KEY / GEMINI_API_KEY) in .env"
    )


def resolve_model(
    agent: PaperInputAgent,
    *,
    override: str | None = None,
) -> str:
    _load_repo_dotenv()
    if override is not None and override.strip():
        return override.strip()
    specific = os.environ.get(model_var(agent), "").strip()
    if specific:
        return specific
    legacy = os.environ.get("GEMINI_MODEL", "").strip()
    if legacy:
        return legacy
    raise RuntimeError(
        f"Missing model for {agent.value}: set {model_var(agent)} "
        f"(or GEMINI_MODEL) in .env"
    )
