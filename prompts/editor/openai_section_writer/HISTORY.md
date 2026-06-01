# Prompt history: `openai_section_writer`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial section writer prompt | LaTeX body per section with citekey pool and figure refs. |
| v002 | 2026-05-22 | Topic lock + JSON-only API note | Section writer could drift to unrelated domains on sparse input; added alignment to manuscript/research only; clarified `json_object` output mode. |
| v003 | 2026-05-26 | Results integrity + mismatch figures | Literature-only research must not appear as study data in Results; Fig.~\\ref for mismatch flags. |
| v004 | 2026-05-27 | Primary 04 source in payload | `primary_manuscript_source` with full text_blocks; source priority over research summaries. |
