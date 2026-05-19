# `research` package

Multi-agent research — **GPT-4o orchestrator**, **two active search agents**, **Gemini report synthesizer**:

| Agent id | Provider | Status |
|----------|----------|--------|
| Orchestrator | OpenAI GPT-4o (tools) | Active — prompt: `research/prompts/openai_orchestrator/` |
| `gemini_search` | Gemini | Active |
| `openai_search` | OpenAI GPT-4o | Active |
| `claude_search` | — | Disabled |
| `exa_search` | — | Disabled |
| `report_synthesizer` | Gemini | Active |

**Flow:** [`src/autopaper/flow/research/README.md`](../src/autopaper/flow/research/README.md)

```bash
pip install -r requirements.txt
research "Your research goal"
```

Configure repo root `.env`: `OPENAI_API_KEY`, `GOOGLE_API_KEY`.
