"""Shared Gemini API helpers for pipeline agents."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Project default (override with GEMINI_MODEL in .env).
_DEFAULT_MODEL = "gemini-1.5-flash"

# Bare "gemini-1.5-flash" often 404s on current API keys; map to a Flash model your key supports.
_GEMINI_15_FLASH_IDS = frozenset(
    {
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-001",
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-8b",
    }
)


def _list_flash_model_ids(api_key: str) -> list[str]:
    try:
        import google.generativeai as genai
    except ImportError:
        return []
    genai.configure(api_key=api_key)
    out: list[str] = []
    for m in genai.list_models():
        methods = getattr(m, "supported_generation_methods", None) or ()
        if "generateContent" not in methods:
            continue
        name = m.name.removeprefix("models/")
        if "flash" in name.lower():
            out.append(name)
    return sorted(out)


def resolve_model_name(
    model_name: str | None = None,
    *,
    api_key: str | None = None,
) -> str:
    if model_name is not None and model_name.strip():
        requested = model_name.strip()
    else:
        requested = os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL

    if requested not in _GEMINI_15_FLASH_IDS:
        return requested

    fallback = os.environ.get("GEMINI_15_FALLBACK", "gemini-2.0-flash").strip()
    if not fallback:
        return requested

    # If strict, use 1.5 as-is (may 404).
    if os.environ.get("GEMINI_STRICT_MODEL", "").strip().lower() in ("1", "true", "yes"):
        return requested

    print(
        f"Note: {requested!r} is not available on many Gemini API keys (404). "
        f"Using {fallback!r} instead. Set GEMINI_STRICT_MODEL=1 to force {requested!r}, "
        f"or set GEMINI_MODEL to a model from your account (e.g. gemini-2.5-flash).",
        file=sys.stderr,
    )
    return fallback


def resolve_api_key(api_key: str | None = None) -> str:
    key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing API key: set GOOGLE_API_KEY or GEMINI_API_KEY (or pass api_key=...)."
        )
    return key


def input_root_from_bundle(bundle: dict[str, Any]) -> Path:
    raw = bundle.get("input_root")
    if not raw or not isinstance(raw, str):
        raise ValueError("raw_input_bundle must contain string input_root")
    return Path(raw).expanduser().resolve()


def safe_file_under_root(root: Path, relative_posix: str) -> Path:
    candidate = (root / relative_posix).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Path escapes input_root: {relative_posix!r}")
    return candidate


def load_pil_images_from_bundle(bundle: dict[str, Any]) -> list[tuple[str, Any]]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Pillow is required to send images to Gemini. Install with: pip install pillow"
        ) from exc

    root = input_root_from_bundle(bundle)
    out: list[tuple[str, Any]] = []
    for rel in bundle.get("image_paths") or []:
        if not isinstance(rel, str):
            continue
        path = safe_file_under_root(root, rel)
        if not path.is_file():
            continue
        out.append((rel, Image.open(path)))
    return out


def generate_json(
    *,
    system_instruction: str,
    content_parts: list[Any],
    api_key: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "google-generativeai is required. Install with: pip install google-generativeai"
        ) from exc

    key = resolve_api_key(api_key)
    genai.configure(api_key=key)
    resolved = resolve_model_name(model_name, api_key=key)
    model = genai.GenerativeModel(
        resolved,
        system_instruction=system_instruction,
    )
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
    )
    try:
        response = model.generate_content(
            content_parts,
            generation_config=generation_config,
        )
    except Exception as exc:
        err = str(exc).lower()
        if "not found" in err or "404" in err:
            flashes = _list_flash_model_ids(key)
            hint = ", ".join(flashes[:8]) if flashes else "(call list_models in AI Studio)"
            raise RuntimeError(
                f"Model {resolved!r} is not available for generateContent on this API key. "
                f"Flash models you can use include: {hint}. "
                f"Set GEMINI_MODEL in .env to one of these. "
                f"Note: gemini-1.5-flash is retired for most keys; use gemini-2.0-flash or gemini-2.5-flash."
            ) from exc
        raise
    text = getattr(response, "text", None) or ""
    if not text.strip():
        raise RuntimeError(
            "Empty response from Gemini (no JSON text). "
            "Check finish_reason / safety filters on the response."
        )
    return json.loads(text)
