"""User-facing provider status and log noise filtering for pipeline runs."""

from __future__ import annotations

import os
import re

# SDK / library messages that should not appear in the run log UI.
_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Both GOOGLE_API_KEY and GEMINI_API_KEY", re.IGNORECASE),
    re.compile(r"Warning:\s*Both GOOGLE_GENAI", re.IGNORECASE),
    re.compile(r"Using GOOGLE_API_KEY\.", re.IGNORECASE),
)


def normalize_provider_env(env: dict[str, str] | None = None) -> None:
    """Drop legacy GEMINI_API_KEY when GOOGLE_API_KEY is set (avoids SDK warnings)."""
    target = os.environ if env is None else env
    if target.get("GOOGLE_API_KEY", "").strip():
        target.pop("GEMINI_API_KEY", None)


def sanitize_subprocess_env(env: dict[str, str]) -> dict[str, str]:
    """Copy env for subprocess with duplicate Gemini keys removed."""
    cleaned = dict(env)
    normalize_provider_env(cleaned)
    return cleaned


def should_hide_user_log_line(line: str) -> bool:
    return any(p.search(line) for p in _NOISE_PATTERNS)


def provider_status_lines() -> list[str]:
    """Human-readable AI provider checklist (no secret values)."""
    openai_ok = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    google_ok = bool(os.environ.get("GOOGLE_API_KEY", "").strip())
    anthropic_ok = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def _mark(ok: bool) -> str:
        return "ready" if ok else "missing"

    lines = [
        "[AutoPaper] AI providers:",
        f"  - OpenAI: {_mark(openai_ok)} (research & editor planning)",
        f"  - Google Gemini: {_mark(google_ok)} (input, search, sections, figures)",
        f"  - Anthropic Claude: {_mark(anthropic_ok)} (research validation & manuscript QA)",
    ]
    missing = [
        name
        for name, ok in (
            ("OPENAI_API_KEY", openai_ok),
            ("GOOGLE_API_KEY", google_ok),
            ("ANTHROPIC_API_KEY", anthropic_ok),
        )
        if not ok
    ]
    if missing:
        lines.append(f"  ! Add to .env: {', '.join(missing)}")
    return lines
