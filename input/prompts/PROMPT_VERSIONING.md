# Prompt versioning (project-wide)

Every prompt **family** (one model / one role) gets its own directory under `input/prompts/<family_name>/`:

| Path | Purpose |
|------|---------|
| `current.md` | **Only** file the application loads at runtime. |
| `archive/vNNN.md` | **Immutable** snapshots; increment `NNN` whenever `current.md` changes. Never overwrite an existing `vNNN.md`. |
| `HISTORY.md` | Human log: date, version id, **why** we changed the prompt, **what problem** the old version had (or what the new one fixes). |

When adding a new family (e.g. another agent), copy this layout and wire a loader in code that reads `<family>/current.md` only.

See `gemini_flash_system/HISTORY.md` for the live example.
