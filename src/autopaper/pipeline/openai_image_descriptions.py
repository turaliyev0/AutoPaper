from __future__ import annotations

import asyncio
import base64
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from autopaper.config import Settings

MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def _image_to_data_url(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large ({len(data)} bytes > {MAX_IMAGE_BYTES})")
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{_guess_mime(path)};base64,{b64}"


async def describe_image_openai(
    image_path: Path,
    relative_posix: str,
    *,
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    key = settings.openai_api_key
    if not key:
        raise RuntimeError("AUTOPAPER_OPENAI_API_KEY is not set")

    owns = client is None
    if client is None:
        client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {key}"},
            timeout=180.0,
        )

    user_text = user_prompt.replace("{{IMAGE_RELATIVE_PATH}}", relative_posix)
    data_url = _image_to_data_url(image_path)

    body: dict[str, Any] = {
        "model": settings.default_model_vision,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    try:
        r = await client.post("/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        return str(data["choices"][0]["message"]["content"])
    finally:
        if owns:
            await client.aclose()


async def describe_images_for_paths(
    root: Path,
    relative_paths: list[str],
    *,
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
) -> list[dict[str, Any]]:
    """Return one record per image path (parallelized, shared client)."""
    root = root.resolve()
    async with httpx.AsyncClient(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": f"Bearer {settings.openai_api_key or ''}"},
        timeout=180.0,
    ) as client:
        sem = asyncio.Semaphore(3)

        async def one(rel: str) -> dict[str, Any]:
            base_rec: dict[str, Any] = {
                "relative_path": rel,
                "absolute_path": str((root / rel).resolve()),
            }
            path = root / rel
            if not path.is_file():
                return {
                    **base_rec,
                    "vision_status": "error",
                    "vision_error": "file_missing",
                    "ai_description": None,
                }
            async with sem:
                try:
                    text = await describe_image_openai(
                        path,
                        rel,
                        settings=settings,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        client=client,
                    )
                    return {
                        **base_rec,
                        "vision_status": "ok",
                        "vision_error": None,
                        "vision_model": settings.default_model_vision,
                        "ai_description": text.strip(),
                    }
                except Exception as exc:  # noqa: BLE001
                    return {
                        **base_rec,
                        "vision_status": "error",
                        "vision_error": str(exc),
                        "ai_description": None,
                    }

        out = await asyncio.gather(*[one(r) for r in relative_paths])
    return list(out)
