"""Step 2: Vision Agent — images only → cleaned image JSON."""

from __future__ import annotations

from typing import Any

from paper_input.agent_env import PaperInputAgent
from paper_input.prompts.loader import load_vision_instruction

from .gemini_client import generate_json, load_images_from_bundle


def _unreadable_entry(relative_path: str, *, reason: str) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "readable": False,
        "description": reason,
        "visible_labels": [],
        "visible_takeaway": "Image not available for visual analysis.",
    }


class VisionAgent:
    """Process all images under images/ from the raw bundle."""

    def __init__(
        self,
        raw_input_bundle: dict[str, Any],
        *,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._bundle = raw_input_bundle
        self._api_key = api_key
        self._model_name = model_name

    def run(self) -> dict[str, Any]:
        from google.genai import types

        loadable, failed = load_images_from_bundle(self._bundle)
        unreadable = [
            _unreadable_entry(
                rel,
                reason="Image file could not be read or encoded (corrupt or truncated).",
            )
            for rel in failed
        ]
        if not loadable:
            return {"images": unreadable}

        content_parts: list[Any] = [
            "Describe each image below. Labels are relative paths under the input project root.\n"
        ]
        for rel, jpeg_bytes in loadable:
            content_parts.append(f"[{rel}]\n")
            content_parts.append(
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
            )

        result = generate_json(
            system_instruction=load_vision_instruction(),
            content_parts=content_parts,
            agent=PaperInputAgent.VISION,
            api_key=self._api_key,
            model_name=self._model_name,
        )
        if unreadable:
            result.setdefault("images", []).extend(unreadable)
        return result
