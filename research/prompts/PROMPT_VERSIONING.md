# Prompt versioning (research package)

Every prompt **family** (one model / one role) lives under `research/prompts/<family_name>/`:

| Path | Purpose |
|------|---------|
| `current.md` | **Only** file loaded at runtime. |
| `archive/vNNN.md` | **Immutable** snapshots; increment `NNN` when `current.md` changes. Never overwrite. |
| `HISTORY.md` | Date, version id, **why** we changed, **what problem** the old version had. |

Wire loaders in `research/prompts/loader.py` (reads `<family>/current.md` only).

Paper-input agents use the same rules under `paper_input/prompts/`.
