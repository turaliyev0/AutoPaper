#!/usr/bin/env python3
"""
Demo: Gemini chat memory + function calling.

  set GOOGLE_API_KEY=...
  python examples/gemini_chat_and_tools_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _key() -> str:
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    if not key:
        raise SystemExit("Set GOOGLE_API_KEY or GEMINI_API_KEY")
    return key


def demo_chat() -> None:
    from autopaper.gemini import GeminiChat

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    chat = GeminiChat(
        api_key=_key(),
        model=model,
        system_instruction="You are a concise research assistant.",
    )
    print("Turn 1:", chat.send("Name three materials used in neural implants."))
    print("Turn 2 (uses memory):", chat.send("Which of those has the lowest Young's modulus?"))


def load_execution_summary(execution_id: str) -> str:
    """Example tool: read a prior AutoPaper run artifact."""
    path = ROOT / "output" / execution_id / "04_final_standardized.json"
    if not path.is_file():
        return f"No file at {path}"
    return path.read_text(encoding="utf-8")[:4000]


def demo_tools() -> None:
    from autopaper.gemini import run_tool_loop

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    result = run_tool_loop(
        api_key=_key(),
        model=model,
        system="Answer using tools when needed. Reply in plain text.",
        user="Load execution_008 summary and list two key topics in one sentence.",
        tools={
            "load_execution_summary": load_execution_summary,
        },
        automatic=False,
    )
    print("Tool loop turns:", result.turns)
    print("Answer:", result.text)


async def demo_async_chat() -> None:
    from autopaper.gemini import AsyncGeminiChat

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    chat = AsyncGeminiChat(api_key=_key(), model=model)
    reply = await chat.send("Say hello in one word.")
    print("Async:", reply)


if __name__ == "__main__":
    import asyncio

    print("=== Chat (stateful) ===")
    demo_chat()
    print("\n=== Function calling ===")
    demo_tools()
    print("\n=== Async chat ===")
    asyncio.run(demo_async_chat())
