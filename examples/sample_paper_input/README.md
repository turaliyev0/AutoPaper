# Sample paper input

Minimal layout for **`autopaper`**: `description/`, `details/`, `images/`, `metadata/`.

## Try it

From the **repository root** (with the project installed: `python -m pip install -e .`):

```bash
autopaper --input examples/sample_paper_input
```

Requires **`GOOGLE_API_KEY`** or **`GEMINI_API_KEY`** and **`GEMINI_MODEL`** in `.env`.

Each run writes under **`<repo>/output/execution_NNN/`**: `01_raw_input_bundle.json`, `02_cleaned_text.json`, `03_cleaned_images.json`, `04_final_standardized.json`, plus `00_run_manifest.json`.

**Figures:** files in `images/` must be valid PNG/JPEG (etc.) that load with Pillow and pass vision validation; tiny solid-color placeholders may be rejected. See [`docs/testing.md`](../../docs/testing.md).

`output/` at repo root is gitignored so local runs do not clutter commits.
