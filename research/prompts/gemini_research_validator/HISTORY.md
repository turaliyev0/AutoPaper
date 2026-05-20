# Prompt history: `gemini_research_validator`

| Version | Date | Summary |
|---------|------|---------|
| v001 | 2026-05-20 | Initial validator: source traceability + summary clarity per task file |
| v002 | 2026-05-20 | key_points check + confidence calibration + design fidelity | v001 only checked `summary` for source traceability; `key_points` items were not checked against sources; `confidence: high` was not flagged even when most critique was inference; no check for false "lacks" claims in design-critique tasks. Added: explicit rule to check `key_points` against sources; confidence calibration check; design fidelity check for false "lacks" assertions. |
| v003 | 2026-05-20 | Figure-text mismatch exception | execution_001 task 06 (figure-text mismatch) was FAILed for having no literature sources, but the task correctly said it was based on manuscript inference — and there are no papers to cite for visual figure-text comparison. Added explicit exception: do not fail/warn a figure-text mismatch task solely for missing peer-reviewed sources when task says grounding is optional. |
| v004 | 2026-05-20 | Harden mismatch exception to hard rule | Second run: validator set verdict:fail and issues:["No sources listed"] for mismatch tasks even though source_notes correctly said "No sources were required." The soft instruction wasn't strong enough. Changed to hard rule: MUST set verdict:pass (or warn for clarity only) when task says grounding optional, never fail solely for missing sources. |
