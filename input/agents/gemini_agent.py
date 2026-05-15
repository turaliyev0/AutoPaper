from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from input.prompts.loader import load_gemini_flash_system_instruction

_DEFAULT_MODEL = "gemini-1.5-flash"


def _default_system_instruction() -> str:
    return load_gemini_flash_system_instruction()


class GeminiProcessor:
    """
    Sends ``raw_input_bundle`` text (relative paths only in the user payload) and
    on-disk images to Gemini 1.5 Flash; returns parsed JSON (dict).
    """

    def __init__(
        self,
        raw_input_bundle: dict[str, Any],
        *,
        api_key: str | None = None,
        model_name: str = _DEFAULT_MODEL,
        system_instruction: str | None = None,
    ) -> None:
        self._bundle = raw_input_bundle
        self._api_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        self._model_name = model_name
        self._system_instruction = (
            system_instruction if system_instruction is not None else _default_system_instruction()
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

    def _user_payload_relative(self) -> dict[str, Any]:
        """Text + image path references; all file paths relative to input_root."""
        return {
            "text_inputs": {
                "description_files": self._bundle.get("description_files") or [],
                "details_files": self._bundle.get("details_files") or [],
                "metadata_json_files": self._bundle.get("metadata_json_files") or [],
            },
            "image_inputs": list(self._bundle.get("image_paths") or []),
        }

    def _load_pil_images(self) -> list[tuple[str, Any]]:
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - runtime env
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

    def process(self) -> dict[str, Any]:
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
            system_instruction=self._system_instruction,
        )

        payload = self._user_payload_relative()
        text_block = (
            "The JSON below lists only paths relative to the input project root. "
            "Images follow this text block in order.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

        content_parts: list[Any] = [text_block]
        labeled = self._load_pil_images()
        if labeled:
            content_parts.append(
                "\nImages (same order as image_inputs):\n"
            )
        for rel, img in labeled:
            content_parts.append(f"[{rel}]\n")
            content_parts.append(img)

        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
        )
        try:
            response = model.generate_content(
                content_parts,
                generation_config=generation_config,
            )
        finally:
            for _, im in labeled:
                try:
                    im.close()
                except Exception:
                    pass

        text = getattr(response, "text", None) or ""
        if not text.strip():
            raise RuntimeError(
                "Empty response from Gemini (no JSON text). "
                "Check finish_reason / safety filters on the response."
            )
        return json.loads(text)
