from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from input.prompts.loader import (
    load_gemini_flash_system_instruction,
    load_gemini_image_description_instruction,
)

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProcessor:
    """
  Two-step Gemini pipeline:

  - :meth:`describe_images` — step 02: images only → ``02_image_descriptions.json``
  - :meth:`render_extraction` — step 03: text bundle + image descriptions → structured JSON

  Model id: ``model_name`` argument or env ``GEMINI_MODEL`` (default ``gemini-2.5-flash``).
    """

    def __init__(
        self,
        raw_input_bundle: dict[str, Any],
        *,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._bundle = raw_input_bundle
        self._api_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        if model_name is not None and model_name.strip():
            self._model_name = model_name.strip()
        else:
            self._model_name = (
                os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
            )

    def _input_root(self) -> Path:
        raw = self._bundle.get("input_root")
        if not raw or not isinstance(raw, str):
            raise ValueError("raw_input_bundle must contain string input_root")
        return Path(raw).expanduser().resolve()

    def _safe_file_under_root(self, relative_posix: str) -> Path:
        root = self._input_root()
        candidate = (root / relative_posix).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Path escapes input_root: {relative_posix!r}")
        return candidate

    def _load_pil_images(self) -> list[tuple[str, Any]]:
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Pillow is required to send images to Gemini. Install with: pip install pillow"
            ) from exc

        out: list[tuple[str, Any]] = []
        for rel in self._bundle.get("image_paths") or []:
            if not isinstance(rel, str):
                continue
            path = self._safe_file_under_root(rel)
            if not path.is_file():
                continue
            out.append((rel, Image.open(path)))
        return out

    def _generate_json(
        self,
        *,
        system_instruction: str,
        content_parts: list[Any],
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError(
                "Missing API key: set GOOGLE_API_KEY or GEMINI_API_KEY (or pass api_key=...)."
            )

        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "google-generativeai is required. Install with: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(
            self._model_name,
            system_instruction=system_instruction,
        )
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
        )
        response = model.generate_content(
            content_parts,
            generation_config=generation_config,
        )
        text = getattr(response, "text", None) or ""
        if not text.strip():
            raise RuntimeError(
                "Empty response from Gemini (no JSON text). "
                "Check finish_reason / safety filters on the response."
            )
        return json.loads(text)

    def describe_images(self) -> dict[str, Any]:
        """
        Step 02: send all images to Gemini; return JSON with per-image descriptions.
        If there are no images, returns ``{"images": []}`` without calling the API.
        """
        labeled = self._load_pil_images()
        if not labeled:
            return {"images": []}

        content_parts: list[Any] = [
            "Describe each image below. Labels are relative paths under the input project root.\n"
        ]
        for rel, img in labeled:
            content_parts.append(f"[{rel}]\n")
            content_parts.append(img)

        try:
            return self._generate_json(
                system_instruction=load_gemini_image_description_instruction(),
                content_parts=content_parts,
            )
        finally:
            for _, im in labeled:
                try:
                    im.close()
                except Exception:
                    pass

    def render_extraction(self, image_descriptions: dict[str, Any]) -> dict[str, Any]:
        """
        Step 03: send text/metadata from the bundle plus step-02 image descriptions;
        return restructured JSON (no raw images).
        """
        text_payload = {
            "description_files": self._bundle.get("description_files") or [],
            "details_files": self._bundle.get("details_files") or [],
            "metadata_json_files": self._bundle.get("metadata_json_files") or [],
        }
        user_message = (
            "Restructure the materials below. Paths are relative to the input project root.\n\n"
            "## raw_input_bundle (text and metadata only)\n\n"
            + json.dumps(text_payload, ensure_ascii=False, indent=2)
            + "\n\n## image_descriptions (from step 02; do not invent extra figure content)\n\n"
            + json.dumps(image_descriptions, ensure_ascii=False, indent=2)
        )
        return self._generate_json(
            system_instruction=load_gemini_flash_system_instruction(),
            content_parts=[user_message],
        )

    def process(self) -> dict[str, Any]:
        """Run step 02 then step 03 (backward-compatible single call)."""
        image_descriptions = self.describe_images()
        return self.render_extraction(image_descriptions)
