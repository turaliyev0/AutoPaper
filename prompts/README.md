# AutoPaper prompts

Consolidated copy of **all system prompts** used by the pipeline.  
**Runtime loaders still read from** `pipeline/{input,research,editor}/prompts/` — update those `current.md` files for live runs, then refresh this folder if you want them in sync.

---

## Layout

| Folder | Stage | Agents |
|--------|-------|--------|
| [`input/`](input/) | 01–04 ingest | Text parser, vision, joiner |
| [`research/`](research/) | 05–08 research | Orchestrator, search, validator, index |
| [`editor/`](editor/) | 09–13 IEEE editor | Orchestrator, section writer, figures, validator |
| [`reference-paperorchestra/`](reference-paperorchestra/) | External reference | PaperOrchestra skill prompts (not wired into AutoPaper runtime) |

Each agent family has:

- **`current.md`** — active system instruction (what the code loads)
- **`HISTORY.md`** — version changelog
- **`archive/`** — older `vNNN.md` snapshots

---

## Active prompts (quick index)

### Input (`prompts/input/`)

| File | Agent | Model (typical) |
|------|-------|-----------------|
| `gemini_text_parser/current.md` | Text parser | Gemini |
| `gemini_image_description/current.md` | Vision | Gemini |
| `gemini_joiner/current.md` | Joiner | Gemini |

### Research (`prompts/research/`)

| File | Agent | Model (typical) |
|------|-------|-----------------|
| `openai_orchestrator/current.md` | Research orchestrator (plan) | GPT |
| `openai_orchestrator/followup.md` | Follow-up refinement | Gemini |
| `gemini_search/current.md` | Literature search | Gemini |
| `openai_search/current.md` | Methods / critique search | Gemini |
| `gemini_research_validator/current.md` | Per-task validation | Gemini |
| `gemini_research_index/current.md` | Research catalog | Gemini |

### Editor (`prompts/editor/`)

| File | Agent | Model (typical) |
|------|-------|-----------------|
| `openai_editor_orchestrator/current.md` | Manuscript plan | GPT |
| `openai_section_writer/current.md` | Section LaTeX | Gemini |
| `python_figure_generator/current.md` | Matplotlib code | Gemini |
| `gemini_ieee_validator/current.md` | IEEE gate | Gemini |

---

## Versioning

See `input/PROMPT_VERSIONING.md` and `research/PROMPT_VERSIONING.md` for bump rules.  
Editor families use per-folder `HISTORY.md`.

---

## Refresh this export

From repo root (PowerShell):

```powershell
Remove-Item -Recurse -Force prompts
Copy-Item -Recurse pipeline\input\prompts    prompts\input
Copy-Item -Recurse pipeline\research\prompts prompts\research
Copy-Item -Recurse pipeline\editor\prompts  prompts\editor
Copy-Item -Recurse prompts-en prompts\reference-paperorchestra  # if present
```

Then restore this `README.md` (or keep it under version control).

---

## Related docs

- [pipeline/input/README.md](../pipeline/input/README.md) — input stage
- [pipeline/research/README.md](../pipeline/research/README.md) — research stage
- API reference: `http://localhost:8000/docs` (Swagger) when the backend is running
