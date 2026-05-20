# Prompt history: `openai_orchestrator`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial inline JSON orchestrator prompt | Single `generate_json` response; no tool delegation. |
| v002 | 2026-05-19 | Versioned `current.md` + OpenAI function calling | User requested GPT-4o tools, disabled claude/exa; prompt lived in Python string. |
| v003 | 2026-05-19 | Research-only focus | Mismatch-aware delegation, deduped gemini/openai tasks, required_outputs = report sections. |
| v004 | 2026-05-19 | Experimental design | Required output + openai task for experimental_design; do not generalize hemispheric design away. |
| v005 | 2026-05-19 | Mandatory grounding | Every subtask must require literature-grounded outputs; synthesizer limited to gathered sources. |
| v006 | 2026-05-20 | Validator + per-task files | `research_validator` replaces orchestrator `report_synthesizer`; runtime builds research index catalog. |
