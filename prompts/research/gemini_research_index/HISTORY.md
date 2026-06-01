# Prompt history: `gemini_research_index`

| Version | Date | Summary |
|---------|------|---------|
| v001 | 2026-05-20 | Research catalog/index only (replaces merged report synthesizer role) |
| v002 | 2026-05-20 | Key claims coverage section | execution_003 index had no mapping between the manuscript's specific quantitative claims (SNR > 15 dB, ~3 GPa, n=12, 180-day) and which research files addressed each one. Added `## Key claims coverage` section that maps each `manuscript.key_claims` entry verbatim to research file(s) or marks "not addressed". |
| v003 | 2026-05-21 | Mandatory DOI verification disclaimer | Manual spot-check found 4/6 sources in a validated "pass" task had errors (wrong DOIs, wrong content descriptions). The index gave no indication that citations need human spot-checking. Added mandatory `## ⚠️ Important: Manual DOI verification required` section with verbatim wording to be reproduced in every index, explaining that validation only checks citation format and that all DOIs must be independently verified before manuscript use. |
| v004 | 2026-05-22 | Topic-neutral DOI disclaimer wording | Replaced SNR/modulus-specific examples in manual-verification checklist with generic threshold/sample-size/duration wording. |
