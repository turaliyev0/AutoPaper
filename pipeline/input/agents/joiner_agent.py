"""Step 3: Joiner Agent — combine cleaned text + cleaned images → final standardized JSON."""

from __future__ import annotations

import json
from typing import Any

from pipeline.input.agent_env import PaperInputAgent
from pipeline.input.prompts.loader import load_joiner_instruction

from .gemini_client import generate_json


class JoinerAgent:
    """Merge Text Parser and Vision outputs with cross-references."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name

    def run(
        self,
        cleaned_text: dict[str, Any],
        cleaned_images: dict[str, Any],
    ) -> dict[str, Any]:
        user_message = (
            "Combine the cleaned text and cleaned images below into one final standardized JSON.\n\n"
            "## cleaned_text\n\n"
            + json.dumps(cleaned_text, ensure_ascii=False, indent=2)
            + "\n\n## cleaned_images\n\n"
            + json.dumps(cleaned_images, ensure_ascii=False, indent=2)
        )
        return generate_json(
            system_instruction=load_joiner_instruction(),
            content_parts=[user_message],
            agent=PaperInputAgent.JOINER,
            api_key=self._api_key,
            model_name=self._model_name,
        )
