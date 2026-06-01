# Prompt history: `gemini_joiner`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial Joiner Agent prompt | Dedicated combine/cross-reference step after separate text and vision agents. |
| v002 | 2026-05-18 | Stricter cross-links + mismatch flags | Joiner `summary` described the pipeline, not the research; weak links (e.g. “Gold” in text → Pt/CNT/Au SNR plot) treated as matches. Added `mismatch_flags`, forbid agent meta-language, require strong links only. |
| v003 | 2026-05-18 | `figure_context` instead of `visible_labels` | Align joiner output with Vision v004: one context sentence per figure, no label arrays. |
| v004 | 2026-05-20 | Richer cross-ref relationships + key_claims + duplicate image flagging + distinct mismatch issues | On neuro_stability run: `relationship` always `"depicts_entity"`; both SNR-mismatch figures got identical `issue` text; duplicate images (image.png = placeholder_figure.png) not flagged; no structured key-claims output. Added: five `relationship` values; `key_claims` top-level array; `duplicate_images` array; rule to write distinct `issue` sentences per mismatch entry. |
| v005 | 2026-05-22 | Topic-neutral cross-link examples | Replaced implant/probe/animal-model and Au/Pt/CNT electrode examples with generic system/population and material-quality examples; JSON-only response format note. |
