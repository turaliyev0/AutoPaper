# Gemini: chat memory and function calling in AutoPaper

## What you are looking for

| Concept | Gemini / SDK name | AutoPaper today |
|---------|-------------------|-----------------|
| **Chat with memory** | **Chats API** — `client.chats.create()` then `send_message()` | Not used; each agent is **one-shot** `generate_content` |
| **Function calling** | **Tools** — `FunctionDeclaration` or Python callables in `config.tools` | Only **Google Search** tool on `exa_search`; no custom tools, no call loop |

There is no separate product called “stateful chat” — memory is **conversation history** kept by a `Chat` session (or by you passing `contents=[...]` manually).

---

## Why function calling “does not work” in the current pipeline

1. **`response_mime_type="application/json"`** — Used in `paper_input` and `research` for structured output. That mode expects **text JSON**, not `function_call` parts. **Do not combine** strict JSON mode with custom function tools in the same request.

2. **No tool loop** — Even if the model returns `response.function_calls`, the code never runs your Python function and never sends `Part.from_function_response` back. Function calling requires **1–N round trips**.

3. **Google Search ≠ your functions** — `types.Tool(google_search=...)` is a built-in grounding tool. It is not the same as declaring `load_paper_bundle` or `search_pubmed`.

4. **Single-turn agents** — TextParser, Vision, Joiner, and each search task are independent calls; nothing carries history unless you add it.

---

## How to implement chat memory

Use the shared helper:

```python
from autopaper.gemini import GeminiChat, AsyncGeminiChat

chat = GeminiChat(
    api_key=key,
    model="gemini-2.0-flash",
    system_instruction="You are the paper ingest assistant.",
)
chat.send("Parse this methods section: ...")
chat.send("Now list inconsistencies with the figures we discussed.")  # sees prior turn
```

Under the hood: `google.genai.Client.chats.create(model=..., config=..., history=...)`.

**When to use in AutoPaper**

| Use case | Recommendation |
|----------|----------------|
| TextParser → Vision → Joiner in one reasoning thread | Optional refactor: one `GeminiChat` instead of three isolated calls |
| User revises a paper run interactively | New CLI: `autopaper chat --execution 008` |
| Research search tasks | Usually stay **stateless** (parallel subtasks) |

**Persistence across process restarts:** SDK chat history is **in-memory** unless you save `chat.history` to disk and pass it back as `history=` on the next `chats.create`.

---

## How to implement function calling

### Option A — SDK automatic (Python callables)

```python
def load_final_json(execution_id: str) -> str:
    """Load 04_final_standardized.json for an execution folder."""
    ...

from google.genai import types
from google import genai

client = genai.Client(api_key=key)
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Summarize the paper in execution_008.",
    config=types.GenerateContentConfig(tools=[load_final_json]),
)
print(response.text)
```

### Option B — Manual loop (full control)

Use `autopaper.gemini.run_tool_loop` with a `dict[str, callable]` registry. See `examples/gemini_chat_and_tools_demo.py`.

### Option C — Structured output **after** tools

1. Run tool loop **without** `response_mime_type="application/json"`.
2. Ask for JSON in the **final** user message, or run a second `generate_content` with JSON mode on the tool results only.

---

## Suggested integration points in AutoPaper

| Agent | Chat memory? | Function tools? |
|-------|--------------|-----------------|
| Orchestrator | Optional (clarifying questions) | `list_subtopics`, `read_04_json` |
| `exa_search` | No | Keep Google Search **or** replace with tool `web_search` |
| Joiner | Yes (text + vision in one session) | `flag_mismatch(image_path, issue)` |
| Interactive CLI | Yes | `run_ingest`, `continue_research` |

---

## Run the demo

```bash
set GOOGLE_API_KEY=your_key
python examples/gemini_chat_and_tools_demo.py
```

---

## References

- [google-genai chats](https://github.com/googleapis/python-genai) — “Chats” section
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) — declare tools + function response round trip
