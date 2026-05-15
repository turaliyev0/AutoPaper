# Sample paper input

Minimal layout for **`autopaper`**: `description/`, `details/`, `images/`, `metadata/`.

## Try it

From the **repository root** (with the project installed: `pip install -e .`):

```bash
# Ingest + manifest only (no Gemini API call)
autopaper --input examples/sample_paper_input --no-ai

# Full pipeline including Gemini (needs GOOGLE_API_KEY or GEMINI_API_KEY)
autopaper --input examples/sample_paper_input
```

Each run creates **`examples/sample_paper_input/output/execution_NNN/`** with `01_raw_input_bundle.json`, `00_run_manifest.json`, and (unless `--no-ai`) `02_ai_extraction.json`.

`examples/**/output/` is gitignored so local runs do not clutter commits.
