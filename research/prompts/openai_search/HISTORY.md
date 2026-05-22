# Prompt history: `openai_search`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-19 | New agent replacing disabled `claude_search` | Prompt was inline in Python. |
| v002 | 2026-05-19 | Versioned `current.md` | Prompt-history rule; distinct from gemini_search voice. |
| v003 | 2026-05-19 | Research pipeline | Figure review + actionable fixes; sources[]; manuscript context. |
| v004 | 2026-05-19 | Design fidelity + citations | Mandate experimental_design critique; anti-textbook; named sources. |
| v005 | 2026-05-19 | Mandatory grounding | Field norms/benchmarks must cite papers; manuscript critique labeled as inference. |
| v006 | 2026-05-20 | Fidelity rule + critique depth + confidence calibration + bullet summary | (see full entry)
| v007 | 2026-05-21 | DOI caution + journal field | Manual spot-check of execution_001 found repeated DOI fabrication across all Gemini documents (wrong journal suffix, preprint server DOIs for 2017 papers, etc.). OpenAI search can do live web lookup so DOI accuracy is better there, but still not guaranteed from memory. Added explicit DOI caution at top: only include doi if retrieved from live search this session, otherwise leave empty; always include journal (abbreviated) so paper is findable without DOI. Added journal field to sources schema. | execution_003 task 04: falsely claimed "manuscript lacks mechanical property details" when Young's modulus, substrate, PEDOT:PSS were all in experimental_design; critique was shallow (4 generic sources, no laterality/power/coating discussion); set `confidence: high` despite mostly inference. Added: fidelity rule forbidding false "lacks" claims; required critique depth checklist (power/n, laterality, coating, duration); confidence calibration rules; bullet-point summary format. |
| v008 | 2026-05-22 | Topic-neutral examples + topic lock | Removed neural/biomedical-specific examples (SNR, laterality, PEDOT, J. Neural Eng., in vivo); design-critique checklist and metrics now domain-neutral; added **Topic lock**; JSON-only API note in output section. |
