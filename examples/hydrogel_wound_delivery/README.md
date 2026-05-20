# Example: hydrogel wound delivery (`hydrogel_wound_delivery`)

Synthetic **paper-input** bundle in the same layout as `examples/neuro_stability/`:

- `description/overview.md` — narrative, hypotheses, figure list
- `details/method_notes.txt` — structured methods / parameters
- `metadata/paper_meta.json` — title, authors, journal target, tags
- `images/*.png` — figures referenced from the overview (real PNGs, not 1×1 placeholders)

## Run

```bash
autopaper --input examples/hydrogel_wound_delivery
```

Requires `GOOGLE_API_KEY` in the environment or repo `.env` (see root `README.MD`).

## Images

Figures are copied from `neuro_stability` only to satisfy vision validation (real image bytes). **Content may not match** the hydrogel narrative; that is intentional for exercising text–vision joiner and mismatch detection during development.
