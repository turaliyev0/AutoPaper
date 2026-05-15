"""Step 2: Vision Agent — images only → cleaned image JSON."""

from __future__ import annotations

from typing import Any

from input.prompts.loader import load_vision_instruction

from .gemini_client import generate_json, load_pil_images_from_bundle


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
        labeled = load_pil_images_from_bundle(self._bundle)
        if not labeled:
            return {"images": []}

        content_parts: list[Any] = [
            "Describe each image below. Labels are relative paths under the input project root.\n"
        ]
        for rel, img in labeled:
            content_parts.append(f"[{rel}]\n")
            content_parts.append(img)

        try:
            return generate_json(
                system_instruction=load_vision_instruction(),
                content_parts=content_parts,
                api_key=self._api_key,
                model_name=self._model_name,
            )
        finally:
            for _, im in labeled:
                try:
                    im.close()
                except Exception:
                    pass
