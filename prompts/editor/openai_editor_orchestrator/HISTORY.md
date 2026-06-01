# Prompt history: `openai_editor_orchestrator`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial editor orchestrator prompt | Tool-only plan: sections, figures, validation focus. |
| v002 | 2026-05-22 | Topic-neutral figure naming | Figure IDs and reuse rules no longer use domain-specific placeholders; `fig_id` must reflect actual manuscript topic. |
| v003 | 2026-05-26 | No orchestrator word caps; hard rules consolidated | Removed `max_words` from mapping; IEEE headings + mismatch_flags guidance in Hard Rules; validation after writing. |
| v004 | 2026-05-26 | Supervisor + research catalog | Index + summary excerpts in context; one slug per section; `primary_sections` on figures; slug duplicate rejection in tools. |
| v005 | 2026-05-26 | Strict validation only | Removed auto-repair/heuristics; plan must pass validate_editor_plan or fail. |
| v006 | 2026-05-26 | assign_research_slug + retry | One tool call per slug; orchestrator retries up to 3 times; finalize blocks missing slugs. |
| v007 | 2026-05-27 | 04 text_blocks in plan | Orchestrator sees source file index; manuscript_parts include source_text_blocks / source_text:fragment. |
