"""OpenAI async client for orchestrator (tools) and openai_search agent."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from autopaper.llm.trace import (
    llm_trace_enabled,
    log_openai_request,
    log_openai_response,
    log_openai_tool_call,
    log_openai_tool_done,
    log_openai_tool_session_start,
    log_openai_tool_turn,
)

from ..config import Settings
from ..utils import extract_json_object
from .base import llm_retry, retry_wait_seconds

logger = logging.getLogger(__name__)


def _tool_names_from_schemas(tools: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names.append(str(fn["name"]))
    return names


def _orchestrator_tools_for_responses(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Chat Completions tool schemas to Responses API ``FunctionToolParam`` shape."""
    out: list[dict[str, Any]] = []
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else None
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        params = fn.get("parameters")
        if not isinstance(params, dict):
            params = {}
        out.append(
            {
                "type": "function",
                "name": name,
                "description": str(fn.get("description") or ""),
                "parameters": params,
                "strict": False,
            },
        )
    return out


def _response_output_item_to_input_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json", exclude_none=True)
    if isinstance(item, dict):
        return item
    raise TypeError(f"Unexpected output item type: {type(item)!r}")


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
    async def generate_json(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_json",
    ) -> dict[str, Any]:
        log_openai_request(
            label=trace_label,
            model=self._model,
            mode="json",
            user_preview=user,
        )
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
        log_openai_response(label=trace_label, content=content)
        return extract_json_object(content)

    @llm_retry(max_attempts=3)
    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        trace_label: str = "generate_text",
    ) -> str:
        log_openai_request(
            label=trace_label,
            model=self._model,
            mode="text",
            user_preview=user,
        )
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
        content = response.choices[0].message.content or ""
        log_openai_response(label=trace_label, content=content)
        return content

    async def run_tool_session(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Callable[..., dict[str, str]]],
        max_turns: int = 12,
        input_items: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Run OpenAI function calling until the model stops calling tools or ``max_turns``.

        Uses the **Responses API** (``client.responses.create``), not Chat Completions.

        Mutates state only via ``tool_handlers`` (e.g. :class:`OrchestratorPlanBuilder`).

        Returns ``input_items`` so callers can continue the session on validation retry.
        """
        responses_tools = _orchestrator_tools_for_responses(tools)
        if input_items is None:
            input_items = [{"type": "message", "role": "user", "content": user}]
        else:
            input_items = list(input_items)
            input_items.append({"type": "message", "role": "user", "content": user})

        if llm_trace_enabled():
            log_openai_tool_session_start(
                model=self._model,
                tool_names=_tool_names_from_schemas(tools),
            )

        for turn in range(max_turns):
            response = None
            last_exc: BaseException | None = None
            for api_attempt in range(6):
                try:
                    response = await self._client.responses.create(
                        model=self._model,
                        instructions=system,
                        input=input_items,
                        tools=responses_tools,
                        tool_choice="auto",
                        temperature=0.2,
                        store=False,
                    )
                    break
                except RateLimitError as exc:
                    last_exc = exc
                    wait_s = retry_wait_seconds(exc) or 5.0
                    logger.warning(
                        "OpenAI rate limit (tool turn %d, retry %d): sleep %.1fs",
                        turn + 1,
                        api_attempt + 1,
                        wait_s,
                    )
                    await asyncio.sleep(wait_s)
                except (APITimeoutError, APIConnectionError) as exc:
                    logger.warning("OpenAI API error (tool turn %d): %s", turn + 1, exc)
                    raise TimeoutError(str(exc)) from exc
            if response is None:
                raise TimeoutError(str(last_exc) if last_exc else "OpenAI API failed")

            if getattr(response, "error", None) is not None:
                err = response.error
                msg = getattr(err, "message", None) or str(err)
                raise RuntimeError(f"Responses API error: {msg}")

            function_calls = [
                item
                for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]
            if llm_trace_enabled():
                log_openai_tool_turn(turn=turn + 1, tool_count=len(function_calls))

            for item in response.output:
                input_items.append(_response_output_item_to_input_dict(item))

            if not function_calls:
                final = getattr(response, "output_text", "") or ""
                if llm_trace_enabled():
                    log_openai_tool_done(turns=turn + 1, final_text=str(final))
                return input_items

            for call in function_calls:
                name = getattr(call, "name", None) or ""
                raw_args = getattr(call, "arguments", None) or "{}"
                call_id = getattr(call, "call_id", None) or ""

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

                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(payload, ensure_ascii=False),
                    },
                )
                logger.debug("Tool %s → %s", name, payload.get("status"))
                if llm_trace_enabled():
                    log_openai_tool_call(name, raw_args, payload)
        raise RuntimeError(f"Orchestrator tool loop exceeded {max_turns} turns.")
