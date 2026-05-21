# Prompt history: `openai_orchestrator`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial inline JSON orchestrator prompt | Single `generate_json` response; no tool delegation. |
| v002 | 2026-05-19 | Versioned `current.md` + OpenAI function calling | User requested GPT-4o tools, disabled claude/exa; prompt lived in Python string. |
| v003 | 2026-05-19 | Research-only focus | Mismatch-aware delegation, deduped gemini/openai tasks, required_outputs = report sections. |
| v004 | 2026-05-19 | Experimental design | Required output + openai task for experimental_design; do not generalize hemispheric design away. |
| v005 | 2026-05-19 | Mandatory grounding | Every subtask must require literature-grounded outputs; synthesizer limited to gathered sources. |
| v006 | 2026-05-20 | Validator + per-task files | `research_validator` replaces orchestrator `report_synthesizer`; runtime builds research index catalog. |
| v007 | 2026-05-20 | Responses API | Orchestrator tool loop uses `POST /v1/responses` via SDK `client.responses.create` (Chat Completions no longer used for tools). |
| v008 | 2026-05-20 | Distinct tasks + key_claims embedding + no meta-outputs | execution_003/008 revealed: (1) two openai_search tasks both critiqued the design (overlapping); (2) `required_outputs` included a "validation-ready summary" which is a pipeline rule, not a research deliverable; (3) orchestrator did not embed specific quantitative values from `key_claims` into tasks. Added: distinct-angle rule (gemini=background/comparable, openai=critique/methods); ban meta-outputs from required_outputs; instruct embedding key_claims numbers into relevant tasks. |
| v009 | 2026-05-20 | Figure-text mismatch grounding exception | execution_001: figure-text mismatch task (task 06) got FAILed by validator because it correctly labeled all claims as manuscript inference with no peer-reviewed sources — but there are no papers to cite for "the PNG shows Pt/CNT/Au while text says Si/Polyimide." Added explicit exception: figure-text mismatch tasks do not require peer-reviewed sources; task description must include "grounding in literature is optional for figure-text mismatch review". |
| v010 | 2026-05-21 | Make mismatch task mandatory + clarify key_claims rule | After wiring key_claims into ManuscriptContext, the orchestrator chose to replace the mismatch task with a quantitative-claims benchmark task. Added hard rule: mismatch review MUST result in a dedicated openai_search subtask when mismatch_flags are present, and the benchmark task cannot replace it. Clarified that key_claims embedding does not displace the mismatch task. |
