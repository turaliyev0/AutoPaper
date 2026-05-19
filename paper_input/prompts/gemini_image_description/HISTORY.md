# Prompt history: `gemini_image_description`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial prompt for pipeline step 02 | Images were processed in the same call as full text restructuring, which encouraged compression. Split image vision into a dedicated step before render. |
| v002 | 2026-05-15 | Brief figure descriptions (archived detailed prompt as v002) | Vision output was overly exhaustive (axis ticks, p-values, long observation lists). User wants readable brief descriptions; numeric detail stays in text parser / joiner from source files, not duplicated from pixels. |
| v003 | 2026-05-18 | Vision-only descriptions; no “supports the study” | On neuro_stability, `scientific_relevance` invented study claims (e.g. CNT superiority) without manuscript context; figure labels (Pt/CNT/Au) were over-interpreted. Replaced with `visible_takeaway` + `visible_labels`. |
| v004 | 2026-05-18 | General `figure_context` sentence, no label arrays | Final JSON listed every legend string in `visible_labels`; users want one high-level context sentence instead of label inventories. |
