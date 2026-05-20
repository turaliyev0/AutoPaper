# `research` package

Multi-agent research — **GPT-4o orchestrator**, **parallel search** (one JSON file per subtask), **validator**, **research index**:

| Agent id | Provider | Status |
|----------|----------|--------|
| Orchestrator | OpenAI GPT-4o (tools) | Active — `research/prompts/openai_orchestrator/` |
| `gemini_search` | Gemini | Active — per-task file under `06_research/` |
| `openai_search` | OpenAI GPT-4o | Active — per-task file under `06_research/` |
| `research_validator` | Gemini | Active — `07_validation/*.validation.json` |
| Research index | Gemini | Active — `08_research_index.md` (catalog, not merged report) |
| `claude_search` | — | Disabled |
| `exa_search` | — | Disabled |

**Flow:** [`src/autopaper/flow/research/README.md`](../src/autopaper/flow/research/README.md)

```bash
pip install -r requirements.txt
research "Your research goal"
```

Configure repo root `.env`: `OPENAI_API_KEY`, `GOOGLE_API_KEY`.
