# AutoPaper

Automated academic paper tooling in two pipelines:

| Pipeline | CLI | Package | Output |
|----------|-----|---------|--------|
| **Paper input** | `autopaper --input <folder>` | `paper_input` | `output/execution_NNN/*.json` |
| **Research** | `research "your goal"` | `research` | `output/research_runs/run_NNN/` (`02_research/`, `03_validation/`, `04_research_index.md`) |

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create a repo root `.env` with your API keys (see **Configuration** below).

**Paper input** (Gemini: text parser, vision, joiner):

```bash
autopaper --input examples/neuro_stability
```

**Research** (GPT-4o plan → parallel search per task → validator → research index catalog):

```bash
research "State of flexible neural implants 2024–2026"
```

## Configuration

Edit repo root `.env`: `GOOGLE_API_KEY` and `OPENAI_API_KEY`; optional per-agent `RESEARCH_*_MODEL` overrides. (`claude_search` / `exa_search` disabled.)

Do not commit secrets. `exa.txt` is local reference only (gitignored).

## Documentation

| Topic | Path |
|-------|------|
| Flow index | [`src/autopaper/flow/README.md`](src/autopaper/flow/README.md) |
| Paper input flow | [`src/autopaper/flow/paper_input/README.md`](src/autopaper/flow/paper_input/README.md) |
| Research flow | [`src/autopaper/flow/research/README.md`](src/autopaper/flow/research/README.md) |
| Package notes | [`paper_input/README.md`](paper_input/README.md), [`research/README.md`](research/README.md) |

## Examples

- `examples/neuro_stability/` — full paper project folder
- `examples/sample_paper_input/` — minimal layout template

## Development

```bash
pip install -r requirements.txt
ruff check paper_input research src
pytest
```
