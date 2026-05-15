# Prompt history: `gemini_flash_system`

Immutable snapshots live under `archive/` as `v001.md`, `v002.md`, …  
The runtime always loads **`current.md`**. Past wording is never deleted from the repo—only copied into `archive/` when you publish a new version.

## Maintainer workflow (do this on every prompt change)

1. Copy **`current.md`** to **`archive/vNNN.md`** where `NNN` is the next integer after the highest existing `v*.md` (e.g. after `v001.md` use `v002.md`). Do not edit archived files later.
2. Edit **`current.md`** with the new system instruction.
3. Append a **new table row** below (same columns). Explain **why** the change was made and **what problem** the old prompt caused (or what goal the new prompt serves).

## Update log

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-14 | Introduced versioned prompt layout | Previously a single flat `gemini_flash_system.md` with no frozen history; we needed an immutable baseline and a documented process so future edits never lose prior wording. This snapshot matches the first English-only JSON contract after removing non-English drafts. |
| v002 | 2026-05-15 | Prompt content update (archived prior `current.md` as v002) | Responses drifted to unrelated examples (e.g. generic “alloy” narratives), dropped technical parameters, and `brief_note` encouraged overly short text. Added **Isolation** and **No information loss** rules; renamed schema field to **`technical_analysis`**. |
| v003 | 2026-05-15 | Restructure-not-summarize pass (archived v002-era `current.md` as v003) | Model still **summarized** dense `method_notes` and similar files despite “no information loss.” Added explicit **Restructure, do not summarize** rules, forbade compression phrases, reframed `summary` as structured inventory only, and required `technical_analysis` to be a full structured transcript. |
