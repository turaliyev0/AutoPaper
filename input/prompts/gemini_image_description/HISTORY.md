# Prompt history: `gemini_image_description`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial prompt for pipeline step 02 | Images were processed in the same call as full text restructuring, which encouraged compression. Split image vision into a dedicated step before render. |
| v002 | 2026-05-15 | Brief figure descriptions (archived detailed prompt as v002) | Vision output was overly exhaustive (axis ticks, p-values, long observation lists). User wants readable brief descriptions; numeric detail stays in text parser / joiner from source files, not duplicated from pixels. |
