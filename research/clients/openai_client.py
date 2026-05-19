"""OpenAI async client for orchestrator (tools) and openai_search agent."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from ..config import Settings
from ..utils import extract_json_object
from .base import llm_retry

logger = logging.getLogger(__name__)


def _tools_trace_enabled() -> bool:
    for name in ("RESEARCH_LOG_TOOLS", "AUTOPAPER_LOG_TOOLS", "AUTOPAPER_GEMINI_LOG"):
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def _emit_tool_call(name: str, raw_args: str, payload: dict[str, str]) -> None:
    print(f"[OpenAI-tools] call {name}({raw_args})", file=sys.stderr, flush=True)
    print(f"[OpenAI-tools] result {name} -> {payload}", file=sys.stderr, flush=True)


def _assistant_message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", None),
        "tool_calls": getattr(message, "tool_calls", None),
    }


class OpenAIClient:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._settings = settings
        key = api_key or settings.orchestrator_api_key
        self._client = AsyncOpenAI(api_key=key)
        self._model = model or settings.orchestrator_model

    @llm_retry(max_attempts=3)
    async def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            logger.warning("OpenAI API error: %s", exc)
            raise TimeoutError(str(exc)) from exc

        content = response.choices[0].message.content or ""
        return extract_json_object(content)

    @llm_retry(max_attempts=3)
    async def generate_text(self, *, system: str, user: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            raise TimeoutError(str(exc)) from exc
        return response.choices[0].message.content or ""

    async def run_tool_session(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Callable[..., dict[str, str]]],
        max_turns: int = 12,
    ) -> None:
        """
        Run OpenAI function calling until the model stops calling tools or ``max_turns``.

        Mutates state only via ``tool_handlers`` (e.g. :class:`OrchestratorPlanBuilder`).
        Do not combine with ``response_format=json_object`` in the same request.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        if _tools_trace_enabled():
            print(
                f"[OpenAI-tools] session start model={self._model} tools={len(tools)}",
                file=sys.stderr,
                flush=True,
            )

        for turn in range(max_turns):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                logger.warning("OpenAI API error (tool turn %d): %s", turn + 1, exc)
                raise TimeoutError(str(exc)) from exc

            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                if getattr(message, "content", None):
                    logger.debug("Orchestrator assistant text (no tools): %s", message.content[:200])
                break

            messages.append(_assistant_message_dict(message))

            for call in tool_calls:
                fn = getattr(call, "function", None)
                name = getattr(fn, "name", None) or ""
                raw_args = getattr(fn, "arguments", None) or "{}"
                call_id = getattr(call, "id", None) or ""

                handler = tool_handlers.get(name)
                if not handler:
                    payload = {"status": "error", "message": f"Unknown tool: {name}"}
                else:
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        if not isinstance(args, dict):
                            args = {}
                        payload = handler(**args)
                    except TypeError as exc:
                        payload = {"status": "error", "message": f"Invalid arguments: {exc}"}
                    except json.JSONDecodeError as exc:
                        payload = {"status": "error", "message": f"Invalid JSON arguments: {exc}"}

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                )
                logger.debug("Tool %s → %s", name, payload.get("status"))
                if _tools_trace_enabled():
                    _emit_tool_call(name, raw_args, payload)
        else:
            raise RuntimeError(f"Orchestrator tool loop exceeded {max_turns} turns.")
