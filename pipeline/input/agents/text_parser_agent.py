"""Step 1: Text Parser Agent — text and metadata only → cleaned text JSON."""

from __future__ import annotations

import json
from typing import Any

from pipeline.input.agent_env import PaperInputAgent
from pipeline.input.prompts.loader import load_text_parser_instruction

from .gemini_client import generate_json


class TextParserAgent:
    """Process description/, details/, and metadata/ from the raw bundle (no images)."""

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
        text_payload = {
            "description_files": self._bundle.get("description_files") or [],
            "details_files": self._bundle.get("details_files") or [],
            "metadata_json_files": self._bundle.get("metadata_json_files") or [],
        }
        user_message = (
            "Parse and restructure the text and metadata below. "
            "Paths are relative to the input project root.\n\n"
            + json.dumps(text_payload, ensure_ascii=False, indent=2)
        )
        return generate_json(
            system_instruction=load_text_parser_instruction(),
            content_parts=[user_message],
            agent=PaperInputAgent.TEXT_PARSER,
            api_key=self._api_key,
            model_name=self._model_name,
        )
