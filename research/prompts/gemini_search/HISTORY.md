# Prompt history: `gemini_search`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Inline prompt in `gemini_search.py` + `base.py` | Adequate but not versioned; shared fragment with openai_search. |
| v002 | 2026-05-19 | Dedicated `current.md` | Align with project prompt-history rule; clearer role boundaries. |
| v003 | 2026-05-19 | Research pipeline | `sources[]` + named refs; manuscript context; confidence cap without sources in code. |
| v004 | 2026-05-19 | Textbook-mode + citations | Ban essay phrases; require authors/year/doi in sources; tie to experimental_design. |
| v005 | 2026-05-19 | Mandatory grounding | Non-negotiable rule: every claim traceable to sources[]; no general-knowledge-only answers. |
| v006 | 2026-05-20 | Bullet summary + authors format + min 4 sources + key_claims check | execution_003 outputs: `summary` was flowing narrative prose despite instructions for bullet format (e.g. "The chronic stability is largely dictated by..."); `authors` field used bare "et al." without first last name; only 6 sources in best case but min was 3. Added: explicit bullet-format requirement for summary with inline citations; first-author-last-name rule in `authors`; minimum 4 sources; instruction to check key_claims quantitative thresholds against comparable literature. |
