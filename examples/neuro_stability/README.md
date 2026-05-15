# Sample paper input

Minimal layout for **`autopaper`**: `description/`, `details/`, `images/`, `metadata/`.

## Try it

From the **repository root** (with the project installed: `python -m pip install -e .`):

```bash
autopaper --input examples/sample_paper_input
```

Requires **`GOOGLE_API_KEY`** or **`GEMINI_API_KEY`** in the environment (export in your shell or use your IDE env).

Each run writes artifacts under **`<repo>/Output/execution_NNN/`** at the AutoPaper project root (not inside this folder). The manifest still records the paper folder as **`input_root`**.

`Output/` at repo root is gitignored so local runs do not clutter commits.
