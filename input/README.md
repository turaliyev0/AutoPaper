# `input` package

Top-level Python package for **paper project folders**: expected directory layout, loading files into a **raw bundle**, allocating **per-run output** directories, **versioned prompts**, and a **Gemini** post-processing step.

Install the project from the repo root:

```bash
python -m pip install -e ".[dev]"
```

On Windows, if `pip` / `python` are not on your `PATH`, use the full interpreter path, e.g.  
`"%LocalAppData%\Programs\Python\Python312\python.exe" -m pip install -e ".[dev]"`  
so both `input` and `autopaper` install correctly.

**Cursor / VS Code:** this repo includes **`.vscode/settings.json`**, which prepends Python 3.12’s install and **Scripts** to `PATH` for **new** integrated terminals. **Close the terminal tab and open a new one** (or reload the window) so `pip` and `autopaper` resolve. If Python is not under `%LocalAppData%\Programs\Python\Python312`, edit that file to match your install.

A ready-made sample you can run against lives at **`examples/sample_paper_input/`** (see its `README.md`).

---

## Folder layout on disk (paper “input root”)

| Subfolder | Role |
|-----------|------|
| `description/` | Text files (`*.md`, `*.txt`, `*.rst` by default). |
| `details/` | Same text patterns as description. |
| `images/` | Raster/vector images allowed by `IMAGE_SUFFIXES` in `layout.py`. |
| `metadata/` | `*.json` files (parsed or error-wrapped in the bundle). |

Run artifacts are written under **`<AutoPaper repo>/Output/execution_NNN/`** (capital **`Output`** next to `input/`, `src/`, etc.). The next run uses one plus the highest existing `execution_<number>` folder there. Override with env **`AUTOPAPER_OUTPUT_DIR`**, the **`output_root`** argument to **`run_ingest_pipeline`**, or CLI **`--output-dir`**.

---

## Public API (`from input import …`)

These names are re-exported from `input/__init__.py`.

### `ingest.py`

| Name | What it does |
|------|----------------|
| **`IMAGE_DESCRIPTIONS_FILENAME`** | Constant: `02_image_descriptions.json` (step 02: Gemini vision on images). |
| **`AI_EXTRACTION_FILENAME`** | Constant: `03_ai_extraction.json` (step 03: restructured text + metadata + image descriptions). |
| **`load_raw_input_bundle(root)`** | Walks `root`, returns a JSON-serializable `dict`: `input_root`, `description_files`, `details_files`, `metadata_json_files` (each file has `relative_path` + content or parsed JSON), and `image_paths` (relative POSIX paths only; no image bytes). |
| **`run_ingest_pipeline(root, *, output_root=None)`** | **Orchestration:** steps 00–01 ingest; step **02** `describe_images()` → `02_image_descriptions.json`; step **03** `render_extraction()` → `03_ai_extraction.json`. Returns `(bundle, run_path)`. Requires API keys for Gemini. |

### `layout.py`

| Name | What it does |
|------|----------------|
| **`TEXT_GLOB_ORDER`** | Tuple of glob patterns used when collecting text files (`*.md`, `*.txt`, `*.rst`). |
| **`IMAGE_SUFFIXES`** | Set of allowed image extensions under `images/`. |
| **`expected_subpaths()`** | Returns the tuple of required subfolder names. |
| **`ensure_input_layout(root)`** | Creates `root` and each expected subfolder if missing. |
| **`verify_input_layout(root)`** | Raises `FileNotFoundError` if any expected subfolder is missing. |

### `run_workspace.py`

| Function | What it does |
|----------|----------------|
| **`resolve_pipeline_output_root(*, override=None)`** | Resolves the base folder for `execution_NNN/`: `override`, then **`AUTOPAPER_OUTPUT_DIR`**, then **`<repo>/Output`**. |
| **`allocate_execution_directory(output_root)`** | Creates `<output_root>/execution_NNN/` with the next integer `NNN` (zero-padded) after the highest existing `execution_<number>` under `output_root`. Retries on `FileExistsError`. |
| **`utc_now_iso()`** | Current UTC timestamp as ISO string (used in manifests). |
| **`write_run_manifest(run_dir, *, pipeline, input_root, extra=None)`** | Writes `00_run_manifest.json` with pipeline id, paths, time, and optional extra fields (for example `steps`). |
| **`append_run_manifest_steps(run_dir, *additional_steps)`** | Merges new step filenames into the `steps` list in an existing manifest (skips if manifest missing). |

### `prompts/loader.py` (import as `input.prompts` or submodule)

| Function | What it does |
|----------|----------------|
| **`prompts_root()`** | `Path` to the `input/prompts` directory. |
| **`load_gemini_flash_system_instruction()`** | Reads the active Gemini system prompt from `prompts/gemini_flash_system/current.md`. |
| **`list_gemini_flash_system_archive_versions()`** | Lists sorted `v*.md` filenames under `gemini_flash_system/archive/`. |

Versioning rules for prompts are documented in **`prompts/PROMPT_VERSIONING.md`** and **`prompts/gemini_flash_system/HISTORY.md`**.

### `agents/gemini_agent.py`

| Class / method | What it does |
|----------------|----------------|
| **`GeminiProcessor(raw_input_bundle, *, api_key=None, model_name=None, system_instruction=None)`** | Holds the ingest bundle; resolves API key from arguments or `GOOGLE_API_KEY` / `GEMINI_API_KEY`; model from `model_name` or **`GEMINI_MODEL`** env or **`gemini-2.5-flash`**; default system text from the versioned prompt loader unless overridden. |
| **`GeminiProcessor.describe_images()`** | Step 02: images only → JSON with per-image descriptions. |
| **`GeminiProcessor.render_extraction(image_descriptions)`** | Step 03: text bundle + step-02 JSON (no pixels) → restructured extraction JSON. |
| **`GeminiProcessor.process()`** | Runs describe_images then render_extraction (both steps). |

---

## Subpackages

| Path | Role |
|------|------|
| **`agents/`** | AI integrations; currently `GeminiProcessor`. |
| **`prompts/`** | Versioned markdown prompts (`<family>/current.md`, `archive/`, `HISTORY.md`) plus `loader.py`. |

---

## Typical usage

```python
from pathlib import Path
from input import run_ingest_pipeline

root = Path("/path/to/paper-folder")
bundle, run_dir = run_ingest_pipeline(root)
```

CLI: `autopaper --input /path/to/paper` (optional **`--output-dir`**). Set **`GOOGLE_API_KEY`** or **`GEMINI_API_KEY`**. Optional **`AUTOPAPER_OUTPUT_DIR`** for a non-default base folder.

---

## Run directory artifacts

| File | Produced by |
|------|-------------|
| `00_run_manifest.json` | `run_ingest_pipeline` (step 00) |
| `01_raw_input_bundle.json` | `run_ingest_pipeline` (step 01) |
| `02_image_descriptions.json` | `run_ingest_pipeline` (step 02: Gemini vision) |
| `03_ai_extraction.json` | `run_ingest_pipeline` (step 03: Gemini render) |
