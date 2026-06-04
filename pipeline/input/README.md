# `pipeline.input` package

Renders **paper project folders** into standardized JSON: layout validation, disk ingest, Gemini agents (text / vision / joiner), and versioned prompts.

**Package path:** `pipeline/input/` (import as `pipeline.input`).

Install from repo root:

```bash
pip install -r requirements.txt
```

---

## Folder layout (paper project root)

| Subfolder | Role |
|-----------|------|
| `description/` | Narrative (`*.md`, `*.txt`, `*.rst`) |
| `details/` | Methods / parameters; add **`results.txt`** or **`results.md`** with measured outcomes (impedance, SNR, histology, *p*-values) so Abstract/Results are not qualitative-only |
| `images/` | Figures |
| `metadata/` | `*.json` |

Artifacts: **`<repo>/output/execution_NNN/`** — override with `AUTOPAPER_OUTPUT_DIR` or `autopaper --output-dir`.

---

## Public API (`from pipeline.input import …`)

| Name | Role |
|------|------|
| `run_ingest_pipeline(root)` | Full pipeline → `(bundle, run_path)` |
| `load_raw_input_bundle(root)` | Disk-only bundle |
| `ensure_input_layout` / `verify_input_layout` | Folder layout |

See `pipeline/input/__init__.py` for exports.

---

## Typical usage

```python
from pathlib import Path
from pipeline.input import run_ingest_pipeline

bundle, run_dir = run_ingest_pipeline(Path("/path/to/your/paper_project"))
```

```bash
autopaper --input /path/to/your/paper_project
```

Or submit via the web UI: `POST /api/runs` (multipart form with overview, methods, results, images).

**Image validation:** after vision, unreadable or missing images stop the pipeline. After joiner, `mismatch_flags` trigger an interactive prompt (TTY), or use `--strict` / `--force-continue-on-mismatch`.

Set `GOOGLE_API_KEY` and per-agent `PAPER_INPUT_*_MODEL` in repo root `.env`.

---

## Subpackages

| Path | Role |
|------|------|
| `agents/` | TextParser, Vision, Joiner + `gemini_client` |
| `prompts/` | Versioned `current.md` per agent family |
