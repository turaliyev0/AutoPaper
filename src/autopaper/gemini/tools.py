"""Function calling loop for Gemini (manual or SDK automatic mode)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types

from .trace import log_request, log_response

logger = logging.getLogger(__name__)

ToolFn = Callable[..., Any]
ToolRegistry = dict[str, ToolFn]


@dataclass
class ToolLoopResult:
    text: str
    function_calls: list[types.FunctionCall] = field(default_factory=list)
    turns: int = 0


def _tool_declarations_from_registry(registry: ToolRegistry) -> list[types.Tool]:
    declarations: list[types.FunctionDeclaration] = []
    for name, fn in registry.items():
        doc = (fn.__doc__ or f"Tool {name}").strip()
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=doc.split("\n")[0] or name,
                # SDK can infer schema from type hints when passing callables directly;
                # explicit declarations need parameters_json_schema.
            ),
        )
    return [types.Tool(function_declarations=declarations)]


def run_tool_loop(
    *,
    api_key: str,
    model: str,
    user: str,
    tools: ToolRegistry | list[Any],
    system: str | None = None,
    max_turns: int = 8,
    automatic: bool = True,
) -> ToolLoopResult:
    """
    Run Gemini with function calling until the model returns text or ``max_turns``.

    **Do not** set ``response_mime_type='application/json'`` in the same request as
    tools — JSON mode and function calls conflict.

    ``tools`` may be:
    - a dict ``{name: callable}`` (manual loop), or
    - a list of Python callables / ``types.Tool`` (SDK automatic mode when ``automatic=True``).
    """
    client = genai.Client(api_key=api_key)
    tool_list: list[Any]
    registry: ToolRegistry = {}

    if isinstance(tools, dict):
        registry = tools
        tool_list = list(registry.values())
    else:
        tool_list = list(tools)

    if automatic and registry:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tool_list,
        )
        log_request(
            label="tool_loop_auto",
            model=model,
            mode="tools_auto",
            tools=[getattr(t, "__name__", str(t)) for t in tool_list],
            user_preview=user,
        )
        response = client.models.generate_content(
            model=model,
            contents=user,
            config=config,
        )
        log_response(response, label="tool_loop_auto")
        return ToolLoopResult(
            text=getattr(response, "text", None) or "",
            turns=1,
        )

    if automatic and not registry:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tool_list,
        )
        log_request(
            label="tool_loop_auto",
            model=model,
            mode="tools_auto",
            tools=[getattr(t, "__name__", str(t)) for t in tool_list],
            user_preview=user,
        )
        response = client.models.generate_content(
            model=model,
            contents=user,
            config=config,
        )
        log_response(response, label="tool_loop_auto")
        return ToolLoopResult(
            text=getattr(response, "text", None) or "",
            turns=1,
        )

    # Manual loop: model proposes calls → we execute → send FunctionResponse
    if isinstance(tools, dict) and not tool_list:
        raise ValueError("tools dict is empty")

    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=tool_list if tool_list else _tool_declarations_from_registry(registry),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part.from_text(text=user)]),
    ]
    all_calls: list[types.FunctionCall] = []

    for turn in range(max_turns):
        log_request(
            label=f"tool_loop_manual_turn_{turn + 1}",
            model=model,
            mode="tools_manual",
            tools=list(registry.keys()),
            user_preview=user if turn == 0 else f"(turn {turn + 1})",
        )
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        log_response(response, label=f"tool_loop_manual_turn_{turn + 1}")
        calls = list(getattr(response, "function_calls", None) or [])
        if not calls:
            return ToolLoopResult(
                text=getattr(response, "text", None) or "",
                function_calls=all_calls,
                turns=turn + 1,
            )

        all_calls.extend(calls)
        if not registry:
            raise RuntimeError("Model returned function calls but no ToolRegistry was provided.")

        call_content = response.candidates[0].content
        contents.append(call_content)

        response_parts: list[types.Part] = []
        for call in calls:
            fn_name = call.name
            try:
                args_str = json.dumps(dict(call.args or {}), ensure_ascii=False)
            except (TypeError, ValueError):
                args_str = str(call.args)
            print(
                f"[Gemini] executing tool {fn_name}({args_str})",
                file=__import__("sys").stderr,
                flush=True,
            )
            fn = registry.get(fn_name or "")
            if not fn:
                payload = {"error": f"Unknown tool: {fn_name}"}
            else:
                try:
                    args = dict(call.args or {})
                    payload = {"result": fn(**args)}
                except Exception as exc:
                    logger.warning("Tool %s failed: %s", fn_name, exc)
                    payload = {"error": str(exc)}
            print(
                f"[Gemini] tool result {fn_name} -> {payload}",
                file=__import__("sys").stderr,
                flush=True,
            )
            response_parts.append(
                types.Part.from_function_response(name=fn_name or "unknown", response=payload),
            )
        contents.append(types.Content(role="tool", parts=response_parts))

    return ToolLoopResult(
        text="",
        function_calls=all_calls,
        turns=max_turns,
    )


async def run_tool_loop_async(
    *,
    api_key: str,
    model: str,
    user: str,
    tools: ToolRegistry | list[Any],
    system: str | None = None,
    max_turns: int = 8,
    automatic: bool = True,
) -> ToolLoopResult:
    """Async wrapper — runs sync loop in thread for now (SDK chat FC is sync-first)."""
    import asyncio

    return await asyncio.to_thread(
        run_tool_loop,
        api_key=api_key,
        model=model,
        user=user,
        tools=tools,
        system=system,
        max_turns=max_turns,
        automatic=automatic,
    )


def parse_json_tool_result(result: ToolLoopResult) -> dict[str, Any]:
    """Parse final text as JSON (for agents that need structured output after tools)."""
    text = result.text.strip()
    if not text:
        raise ValueError("Empty tool-loop response")
    return json.loads(text)
