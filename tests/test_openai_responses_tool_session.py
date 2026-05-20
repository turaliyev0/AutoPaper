"""Mocked OpenAI Responses API tool loop for orchestrator."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from research.agents.orchestrator_tools import ORCHESTRATOR_TOOL_SCHEMAS, OrchestratorPlanBuilder
from research.clients.openai_client import OpenAIClient
from research.config import Settings


class _DumpModel:
    """Minimal stand-in for Responses output items with ``model_dump``."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        # mirror SDK attributes used by run_tool_session
        for k, v in payload.items():
            setattr(self, k, v)

    def model_dump(self, *, mode: str | None = None, exclude_none: bool = True) -> dict[str, Any]:
        return dict(self._payload)


class _FakeResponse:
    def __init__(self, output: list[Any]) -> None:
        self.output = output
        self.error = None

    @property
    def output_text(self) -> str:
        return ""


def _fc(name: str, args: dict[str, Any], call_id: str) -> _DumpModel:
    return _DumpModel(
        {
            "type": "function_call",
            "name": name,
            "arguments": json.dumps(args),
            "call_id": call_id,
        },
    )


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-unit-tests")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    return Settings(_env_file=None)


def test_run_tool_session_responses_loop_finalizes_plan(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = OrchestratorPlanBuilder(settings)
    idx = {"i": 0}

    class _FakeResponses:
        async def create(self, **kwargs: Any) -> _FakeResponse:
            i = idx["i"]
            idx["i"] += 1
            if i == 0:
                return _FakeResponse(
                    [
                        _fc(
                            "set_research_goal",
                            {"main_topic": "T", "required_outputs": ["o1"]},
                            "c0",
                        ),
                    ],
                )
            if i == 1:
                return _FakeResponse([_fc("delegate_gemini_search", {"tasks": ["g"]}, "c1")])
            if i == 2:
                return _FakeResponse([_fc("delegate_openai_search", {"tasks": ["o"]}, "c2")])
            if i == 3:
                return _FakeResponse(
                    [_fc("delegate_research_validation", {"tasks": ["v1"]}, "c3")],
                )
            if i == 4:
                return _FakeResponse([_fc("finalize_orchestrator_plan", {}, "c4")])
            return _FakeResponse(
                [_DumpModel({"type": "message", "role": "assistant", "content": []})],
            )

    client = OpenAIClient(settings)
    monkeypatch.setattr(client._client, "responses", _FakeResponses())

    async def _run() -> None:
        await client.run_tool_session(
            system="You are a test orchestrator.",
            user="Plan research.",
            tools=ORCHESTRATOR_TOOL_SCHEMAS,
            tool_handlers=builder.tool_handlers(),
        )

    asyncio.run(_run())

    assert idx["i"] == 6  # 5 tool turns + 1 no-tool turn
    assert builder.is_complete()
    plan = builder.to_plan()
    assert plan.research_goal.main_topic == "T"


def test_orchestrator_tools_for_responses_shape() -> None:
    from research.clients.openai_client import _orchestrator_tools_for_responses

    converted = _orchestrator_tools_for_responses(ORCHESTRATOR_TOOL_SCHEMAS)
    assert len(converted) == len(ORCHESTRATOR_TOOL_SCHEMAS)
    for t in converted:
        assert t["type"] == "function"
        assert "name" in t and "parameters" in t
        assert t.get("strict") is False
