# `research` package

Multi-agent research — **GPT orchestrator (first call only)**, **Gemini** for everything else:

| Agent id | Provider | Status |
|----------|----------|--------|
| Orchestrator (initial plan) | OpenAI GPT (tools) | Active — `research/prompts/openai_orchestrator/` |
| Orchestrator (follow-up) | Gemini (JSON) | Active — `research/prompts/openai_orchestrator/followup.md` |
| `gemini_search` | Gemini | Active — per-task file under `06_research/` |
| `openai_search` | Gemini (critique role) | Active — per-task file under `06_research/` |
| `research_validator` | Gemini | Active — `07_validation/*.validation.json` |
| Research index | Gemini | Active — `08_research_index.md` (catalog, not merged report) |
| `claude_search` | — | Disabled |
| `exa_search` | — | Disabled |

**Package path:** `pipeline/research/` (import as `pipeline.research`).

```bash
pip install -r requirements.txt
research "Your research goal"
```

Configure repo root `.env`: `OPENAI_API_KEY`, `GOOGLE_API_KEY`.
