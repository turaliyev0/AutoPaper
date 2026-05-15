# Prompt history: `gemini_image_description`

| Version | Date (UTC) | Why we updated | What was wrong / goal |
|---------|------------|----------------|------------------------|
| v001 | 2026-05-15 | Initial prompt for pipeline step 02 | Images were processed in the same call as full text restructuring, which encouraged compression. Split image vision into a dedicated step before render. |
