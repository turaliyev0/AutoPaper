# Sample paper input

Minimal layout for **`autopaper`**: `description/`, `details/`, `images/`, `metadata/`.

## Try it

From the **repository root** (with the project installed: `python -m pip install -e .`):

```bash
autopaper --input examples/sample_paper_input
```

Requires **`GOOGLE_API_KEY`** or **`GEMINI_API_KEY`** in the environment (export in your shell or use your IDE env).

Each run writes under **`<repo>/Output/execution_NNN/`**: `01_raw_input_bundle.json`, `02_image_descriptions.json`, `03_ai_extraction.json`, plus `00_run_manifest.json`.

`Output/` at repo root is gitignored so local runs do not clutter commits.
