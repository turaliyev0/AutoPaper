"""Backward-compatible facade over Text Parser, Vision, and Joiner agents."""

from __future__ import annotations

from typing import Any

from .joiner_agent import JoinerAgent
from .text_parser_agent import TextParserAgent
from .vision_agent import VisionAgent


class GeminiProcessor:
    """
    Runs the three-agent pipeline in order:

    1. :class:`TextParserAgent` → cleaned text JSON
    2. :class:`VisionAgent` → cleaned image JSON
    3. :class:`JoinerAgent` → final standardized JSON
    """

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

    def parse_text(self) -> dict[str, Any]:
        return TextParserAgent(
            self._bundle, api_key=self._api_key, model_name=self._model_name
        ).run()

    def describe_images(self) -> dict[str, Any]:
        """Alias for :meth:`run_vision` (legacy name)."""
        return self.run_vision()

    def run_vision(self) -> dict[str, Any]:
        return VisionAgent(
            self._bundle, api_key=self._api_key, model_name=self._model_name
        ).run()

    def join(
        self,
        cleaned_text: dict[str, Any],
        cleaned_images: dict[str, Any],
    ) -> dict[str, Any]:
        return JoinerAgent(api_key=self._api_key, model_name=self._model_name).run(
            cleaned_text, cleaned_images
        )

    def render_extraction(self, image_descriptions: dict[str, Any]) -> dict[str, Any]:
        """Legacy: expects only image JSON; re-parses text then joins (prefer :meth:`join`)."""
        cleaned_text = self.parse_text()
        return self.join(cleaned_text, image_descriptions)

    def process(self) -> dict[str, Any]:
        cleaned_text = self.parse_text()
        cleaned_images = self.run_vision()
        return self.join(cleaned_text, cleaned_images)
