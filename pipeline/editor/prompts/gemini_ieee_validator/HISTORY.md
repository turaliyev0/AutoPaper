# Prompt history: `gemini_ieee_validator`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial IEEE validator prompt | Per-section JSON verdict (pass/warn/fail). |
| v002 | 2026-05-22 | Topic-neutral leakage note + JSON-only | Removed "neuroscience papers" from pipeline-leakage DO NOT flag list; added JSON-only API instruction. |
| v003 | 2026-05-27 | Strict pre-submission gate + score 0–100 | Structured issues with severity/step; Results/Methods/Abstract integrity steps; mismatch_flags critical; score-based rewrite threshold in pipeline. |
