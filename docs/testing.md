# Testing AutoPaper

## Automated tests (no API keys)

From the repository root with the package installed (`pip install -e .`):

```bash
python -m pytest tests/ -q
```

All tests under [`tests/`](../tests/) are designed to run **without** calling Gemini or OpenAI live APIs. The orchestrator Responses loop is covered with mocks in [`tests/test_openai_responses_tool_session.py`](../tests/test_openai_responses_tool_session.py).

### Optional live integration

If you add tests marked `@pytest.mark.integration` that require keys, run them explicitly:

```bash
python -m pytest tests/ -m integration -q
```

There are no integration-marked tests in the default suite yet; contributors stay unblocked when `.env` is missing.

## Manual smoke (requires keys)

Set `GOOGLE_API_KEY` (and `OPENAI_API_KEY` if you continue past step 04).

**Paper input only** (stops after `04_final_standardized.json`):

```bash
python -m autopaper.main.app --input examples/sample_paper_input --no-research --force-continue-on-mismatch
python -m autopaper.main.app --input examples/neuro_stability --no-research --force-continue-on-mismatch
```

Use `--force-continue-on-mismatch` in scripts when joiner emits `mismatch_flags` and there is no TTY.

**Full research** (uses both Google and OpenAI; costs tokens):

```bash
python -m autopaper.main.app --input examples/neuro_stability --full-research --force-continue-on-mismatch
```

## Example images

Figures under `examples/*/images/` must be **valid image files** that pass disk read and the vision step. A 1×1 solid-color PNG may be rejected as a non-informative placeholder. Prefer a small real figure (e.g. copied from another example) or an exported plot from your project.

## When to change prompts

Update [`research/prompts/`](../research/prompts/) or [`paper_input/prompts/`](../paper_input/prompts/) only when a **concrete** failure mode appears (bad JSON shape, missed `mismatch_flags`, orchestrator skipping a required tool, etc.). Follow each family’s `HISTORY.md` and `PROMPT_VERSIONING.md` (archive prior `current.md` as `archive/vNNN.md`).
