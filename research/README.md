# `research` package

Multi-agent research with **three parallel search agents** and one **report synthesizer**:

| Agent | Technology |
|-------|------------|
| `gemini_search` | Google Gemini |
| `claude_search` | Anthropic Claude |
| `exa_search` | Exa deep web search |
| `report_synthesizer` | Claude (final Markdown) |

**Flow:** [`src/autopaper/flow/research/README.md`](../src/autopaper/flow/research/README.md)

```bash
pip install -r requirements.txt
research "Your research goal"
```

Configure repo root `.env` (shared provider keys + per-agent models).
