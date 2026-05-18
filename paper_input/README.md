# `paper_input` package

Renders **paper project folders** into standardized JSON: layout validation, disk ingest, Gemini agents (text / vision / joiner), and versioned prompts.

**Flow diagram:** [`src/autopaper/flow/paper_input/README.md`](../src/autopaper/flow/paper_input/README.md)

Install from repo root:

```bash
pip install -r requirements.txt
```

---

## Folder layout (paper project root)

| Subfolder | Role |
|-----------|------|
| `description/` | Narrative (`*.md`, `*.txt`, `*.rst`) |
| `details/` | Methods / parameters |
| `images/` | Figures |
| `metadata/` | `*.json` |

Artifacts: **`<repo>/output/execution_NNN/`** — override with `AUTOPAPER_OUTPUT_DIR` or `autopaper --output-dir`.

---

## Public API (`from paper_input import …`)

| Name | Role |
|------|------|
| `run_ingest_pipeline(root)` | Full pipeline → `(bundle, run_path)` |
| `load_raw_input_bundle(root)` | Disk-only bundle |
| `ensure_input_layout` / `verify_input_layout` | Folder layout |

See `paper_input/__init__.py` for exports.

---

## Typical usage

```python
from pathlib import Path
from paper_input import run_ingest_pipeline

bundle, run_dir = run_ingest_pipeline(Path("examples/neuro_stability"))
```

```bash
autopaper --input examples/neuro_stability
```

Set per-agent keys in `.env` (see `.env.example`): `PAPER_INPUT_TEXT_PARSER_*`, `PAPER_INPUT_VISION_*`, `PAPER_INPUT_JOINER_*`, or shared `GOOGLE_API_KEY` + `GEMINI_MODEL`.

---

## Subpackages

| Path | Role |
|------|------|
| `agents/` | TextParser, Vision, Joiner + `gemini_client` |
| `prompts/` | Versioned `current.md` per agent family |
