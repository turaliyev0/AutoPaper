# Prompt history: `gemini_joiner`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial Joiner Agent prompt | Dedicated combine/cross-reference step after separate text and vision agents. |
| v002 | 2026-05-18 | Stricter cross-links + mismatch flags | Joiner `summary` described the pipeline, not the research; weak links (e.g. “Gold” in text → Pt/CNT/Au SNR plot) treated as matches. Added `mismatch_flags`, forbid agent meta-language, require strong links only. |
| v003 | 2026-05-18 | `figure_context` instead of `visible_labels` | Align joiner output with Vision v004: one context sentence per figure, no label arrays. |
