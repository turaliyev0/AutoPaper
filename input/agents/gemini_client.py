"""Shared Gemini API helpers for pipeline agents."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_dotenv_loaded = False


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[2]


def _load_repo_dotenv() -> None:
    """Load ``<repo>/.env`` into ``os.environ`` (does not override existing vars)."""
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


def _make_client(api_key: str):
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "google-genai is required. Install with: pip install google-genai"
        ) from exc
    return genai.Client(api_key=api_key)


def _list_flash_model_ids(api_key: str) -> list[str]:
    try:
        client = _make_client(api_key)
    except ImportError:
        return []
    out: list[str] = []
    for m in client.models.list():
        name = (getattr(m, "name", None) or "").removeprefix("models/")
        if "flash" in name.lower():
            out.append(name)
    return sorted(out)


def resolve_model_name(model_name: str | None = None) -> str:
    """
    Model id from ``model_name`` argument or ``GEMINI_MODEL`` in ``.env`` / environment.

    No built-in fallback models — set ``GEMINI_MODEL`` in the repo ``.env``.
    """
    _load_repo_dotenv()
    if model_name is not None and model_name.strip():
        return model_name.strip()
    env_model = os.environ.get("GEMINI_MODEL", "").strip()
    if env_model:
        return env_model
    raise RuntimeError(
        "Missing model: set GEMINI_MODEL in the repository .env (or pass model_name=...)."
    )


def resolve_api_key(api_key: str | None = None) -> str:
    _load_repo_dotenv()
    key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing API key: set GOOGLE_API_KEY or GEMINI_API_KEY in .env "
            "(or pass api_key=...)."
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


def _encode_image_bytes(path: Path) -> bytes:
    import io

    from PIL import Image

    with Image.open(path) as im:
        im.load()
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def load_images_from_bundle(
    bundle: dict[str, Any],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """
    Return ``(loadable, failed)`` as ``(relative_path, jpeg_bytes)`` pairs and paths
    that could not be read or encoded (corrupt/truncated files).
    """
    try:
        from PIL import Image  # noqa: F401 — import check
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Pillow is required to send images to Gemini. Install with: pip install pillow"
        ) from exc

    root = input_root_from_bundle(bundle)
    loadable: list[tuple[str, bytes]] = []
    failed: list[str] = []
    for rel in bundle.get("image_paths") or []:
        if not isinstance(rel, str):
            continue
        path = safe_file_under_root(root, rel)
        if not path.is_file():
            failed.append(rel)
            continue
        try:
            loadable.append((rel, _encode_image_bytes(path)))
        except OSError:
            failed.append(rel)
    return loadable, failed


def load_pil_images_from_bundle(bundle: dict[str, Any]) -> list[tuple[str, Any]]:
    """Deprecated: use :func:`load_images_from_bundle`."""
    loadable, _ = load_images_from_bundle(bundle)
    return loadable


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text and str(text).strip():
        return str(text)
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if part_text and str(part_text).strip():
                return str(part_text)
    return ""


def generate_json(
    *,
    system_instruction: str,
    content_parts: list[Any],
    api_key: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    try:
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "google-genai is required. Install with: pip install google-genai"
        ) from exc

    key = resolve_api_key(api_key)
    client = _make_client(key)
    resolved = resolve_model_name(model_name)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
    )
    try:
        response = client.models.generate_content(
            model=resolved,
            contents=content_parts,
            config=config,
        )
    except Exception as exc:
        err = str(exc).lower()
        if "not found" in err or "404" in err:
            flashes = _list_flash_model_ids(key)
            hint = ", ".join(flashes[:8]) if flashes else "(check models in Google AI Studio)"
            raise RuntimeError(
                f"Model {resolved!r} is not available for generateContent on this API key. "
                f"Flash models you can use include: {hint}. "
                f"Set GEMINI_MODEL in .env to one of these."
            ) from exc
        raise
    text = _response_text(response)
    if not text.strip():
        raise RuntimeError(
            "Empty response from Gemini (no JSON text). "
            "Check finish_reason / safety filters on the response."
        )
    return json.loads(text)
