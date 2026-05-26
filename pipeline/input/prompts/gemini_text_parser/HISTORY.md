# Prompt history: `gemini_text_parser`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial Text Parser Agent prompt | Split monolithic render step: text/metadata processed alone before vision and join. |
| v002 | 2026-05-20 | Verbatim headings + key_claims + citation_gap | On neuro_stability run: title was paraphrased ("A Comprehensive Analysis" added by model); no structured hypothesis extraction; no flag when text lacks bibliographic citations. Added: preserve headings verbatim rule; `key_claims` array per text_block; `citation_gap: true` flag when no citations present. |
| v003 | 2026-05-22 | Topic-neutral examples + JSON-only note | Replaced SNR/Young's modulus key_claims examples with generic metrics; response format states JSON-only API mode. |
| v004 | 2026-05-22 | Restore corrupted current.md + JSON string safety | `current.md` had been overwritten with raw method_notes text (not a prompt), causing malformed JSON from the model. Restored full parser prompt; added **JSON string safety** rules (escape quotes/newlines, no trailing commas). |
