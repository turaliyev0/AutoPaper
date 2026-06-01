# AutoPaper — options catalog for the frontend

Reference for UI controls (toggles, selects, checkboxes) mapped to pipeline data and run settings.  
Artifact: **`04_final_standardized.json`** (step 04) is the main “options surface” after ingest; many fields are **set by AI** today but can be **shown and overridden** in the UI after a preview step.

---

## Legend

| Column | Meaning |
|--------|---------|
| **UI control** | Suggested frontend widget |
| **Set by** | `user` (submit form), `pipeline` (agents), or `either` |
| **API today** | Whether `POST /api/runs` or `/api/config` already exposes this |

---

## 1. Run submission (implement first)

These map to **`POST /api/runs`** (`main.py`) and **`GET /api/config`**.

| Option | Type | Values | Default | UI control | Set by | API today |
|--------|------|--------|---------|------------|--------|-----------|
| `title` | string | — | required | Text input | user | Yes (`Form`) |
| `overview` | string | markdown | required | Textarea | user | Yes → `description/overview.md` |
| `methods` | string | plain text | `""` | Textarea | user | Yes → `details/method_notes.txt` |
| `authors` | string | comma-separated | `""` | Text input | user | Yes → `metadata/paper_meta.json` |
| `affiliation` | string | — | `""` | Text input | user | Yes |
| `target_journal` | string | — | `"IEEE"` | Text input | user | Yes |
| `ieee_format` | enum | `journal`, `conference` | `journal` | Radio / select | user | Yes |
| `images` | files | PNG, JPEG, WebP | `[]` | File upload (max 10) | user | Yes |
| `results` | string | measured outcomes | — | Textarea (recommended) | user | **No** — add field → `details/results.txt` |

**Recommended extra field (not in API yet):**

```http
POST /api/runs
  results: <textarea>   → details/results.txt
```

Without `results.txt`, Abstract/Results stay qualitative even when methods are complete (see `pipeline/input/templates/details_results.example.txt`).

### Pipeline stages (CLI flags — expose as “Advanced” checkboxes)

| Option | CLI flag | Default (API runner) | UI control | API today |
|--------|----------|----------------------|------------|-----------|
| Full research | `--full-research` | on | Checkbox (on) | Hard-coded in `pipeline_runner.py` |
| IEEE editor + PDF | `--ieee-edit` | on | Checkbox (on) | Hard-coded |
| Editor live log | `--log-editor` | on | Checkbox | Hard-coded |
| Mismatch: continue | `--force-continue-on-mismatch` | on | Select (see §3) | Hard-coded |
| Mismatch: strict stop | `--strict` | off | Select | No |
| Ingest only | `--no-research` | off | Checkbox | No |
| Editor only | `--editor-only` + `execution_dir` | off | Run detail action | No |
| Resume editor | `--editor-resume` | off | Run detail action | No |

---

## 2. `04_final_standardized.json` — top-level keys

Path: `output/execution_NNN/04_final_standardized.json`

| Key | Type | Example | Meaning | UI control | Set by |
|-----|------|---------|---------|------------|--------|
| `summary` | string | markdown blob | Joined narrative for orchestrator | Read-only preview + optional edit | pipeline |
| `key_claims` | `string[]` | `"Channel count: 16 channels"` | Flattened quantitative claims | Tag list; add/remove | pipeline (user override optional) |
| `text_blocks` | array | see §3 | Per-file parsed content | Accordion per file | pipeline |
| `metadata_notes` | array | `key_points` strings | From `metadata/*.json` | Read-only | pipeline |
| `images` | array | vision output | Usable figures | Gallery + per-image flags | pipeline |
| `cross_references` | array | text↔image links | Strong links only | Link editor | pipeline |
| `mismatch_flags` | array | see §4 | Figure vs text conflicts | Warning list + actions | pipeline |
| `duplicate_images` | array | `{original, duplicate}` | Identical figures | Pair list | pipeline |
| `excluded_images` | array | `{path, reason, issue}` | Never use in PDF | Blocked list (read-only) | pipeline (derived) |

---

## 3. Per text block (`text_blocks[]`)

Each item:

```json
{
  "relative_path": "description/overview.md",
  "technical_analysis": "...",
  "key_claims": [
    { "claim": "...", "evidence_path": "description/overview.md" }
  ],
  "citation_gap": true,
  "linked_images": ["images/fig1.png"]
}
```

| Field | Type | Values | Meaning | UI control | Set by |
|-------|------|--------|---------|------------|--------|
| `relative_path` | string | project-relative | Source file | Label (read-only) | pipeline |
| `technical_analysis` | string | markdown | Parsed body | Expandable editor | pipeline |
| `key_claims` | object[] | `claim`, `evidence_path` | Testable claims in this file | Nested list | pipeline |
| **`citation_gap`** | **boolean** | `true` / `false` | **`true`**: no in-text citations in source → research should add literature | **Toggle per block** | pipeline (text parser) |
| `linked_images` | string[] | paths under `images/` | Joiner-approved figure links | Multi-select from uploaded images | pipeline |

### `citation_gap` — frontend behavior

| Value | Show in UI | Pipeline effect |
|-------|------------|-----------------|
| `true` | Badge: “Needs citations” | Research orchestrator assigns more `gemini_search` background tasks; Introduction/Background writers should cite from pool |
| `false` | Badge: “Citations present in source” | Normal literature support |

**Suggested UX:** After ingest preview (step 04), list each `text_blocks[]` row with:

```
[ ] citation_gap   description/overview.md
[x] citation_gap   details/method_notes.txt
```

User override → PATCH merged into `04` before research (API not implemented yet).

---

## 4. `mismatch_flags[]`

Produced by the **Joiner** when a figure disagrees with manuscript text.

```json
{
  "image_path": "images/fig1.png",
  "text_paths": ["description/overview.md"],
  "issue": "Figure shows X; manuscript text describes Y.",
  "severity": "likely_mismatch"
}
```

| Field | Type | Values | UI control | Set by |
|-------|------|--------|------------|--------|
| `image_path` | string | — | Thumbnail + path | pipeline |
| `text_paths` | string[] | — | Chips linking to blocks | pipeline |
| `issue` | string | — | Textarea (editable) | pipeline |
| **`severity`** | **enum** | see below | **Select** | pipeline |

### `severity` values

| Value | UI label | User action | Pipeline effect |
|-------|----------|-------------|-----------------|
| `likely_mismatch` | Serious mismatch | Exclude figure or fix text | Image → `excluded_images`; not used as `reuse_path` |
| `unclear` | Unclear | Review | Prompt on CLI; API continues with `--force-continue-on-mismatch` |
| `weak_overlap` | Weak overlap | Review | Same as `unclear` |

**Run-level policy (§1):** map to a select:

| UI option | CLI |
|-----------|-----|
| Continue on warnings | `--force-continue-on-mismatch` (default API) |
| Ask me (TTY only) | `MismatchPolicy.AUTO` |
| Stop on any mismatch | `--strict` |

---

## 5. `cross_references[]`

```json
{
  "text_path": "description/overview.md",
  "image_path": "images/device.png",
  "relationship": "depicts_device"
}
```

| `relationship` | UI label | Use when |
|----------------|----------|----------|
| `depicts_device` | Depicts device | Figure shows hardware described in text |
| `provides_measurement_data` | Provides data | Figure is a result plot |
| `supports_hypothesis` | Supports hypothesis | Figure supports a stated claim |
| `depicts_entity` | Depicts entity | Material/setup/subject without implying data |
| `contradicts_text` | Contradicts text | Conflicts with text (often also a `mismatch_flag`) |

**UI control:** Select per link; optional “Add cross-reference” dialog.

---

## 6. `images[]` (vision output)

| Field | Type | Values | UI control | Set by |
|-------|------|--------|------------|--------|
| `relative_path` | string | — | Thumbnail | pipeline |
| `description` | string | — | Read-only / edit | pipeline |
| `figure_context` | string | one sentence | Read-only / edit | pipeline |
| `readable` | boolean | `true` / `false` | Status icon | pipeline |
| `mentioned_in_text` | boolean | optional | Checkbox | pipeline |
| `duplicate_of` | string | path | Badge “duplicate” | pipeline |
| `excluded` | boolean | optional | Badge “excluded” | pipeline (derived) |
| `exclusion_reason` | string | `likely_mismatch`, `duplicate` | Tooltip | pipeline |

**Fatal:** `readable: false` or disk read failure → ingest stops (no continue).

---

## 7. `duplicate_images[]`

```json
{ "original": "images/fig_a.png", "duplicate": "images/fig_b.png" }
```

| UI control | Action |
|------------|--------|
| List pairs | Show which file is dropped (`duplicate` path excluded) |
| Button “Keep both” | Remove pair (override before research — API TBD) |

---

## 8. `excluded_images[]` (read-only summary)

Derived from `likely_mismatch` flags and duplicates. Do not offer as manuscript figures.

| `reason` | Meaning |
|----------|---------|
| `likely_mismatch` | Excluded by severity |
| `duplicate` | Duplicate copy removed |

**UI:** Red “Excluded from manuscript” strip on image cards.

---

## 9. Editor plan (`09_editor_plan.json`) — optional advanced UI

After editor orchestrator (step 09):

| Field | Type | UI idea |
|-------|------|---------|
| `ieee_format` | `journal` \| `conference` | Same as submit (should match) |
| `sections[].research_slugs` | string[] | Drag-drop slug → section |
| `sections[].manuscript_parts` | string[] | Multi-select: `summary`, `key_claims`, `source_text:method`, … |
| `figures[].data_hints` | string[] | List editor for synthetic plots |
| `figures[].reuse_path` | string | Image picker (non-excluded only) |
| `figures[].primary_sections` | string[] | e.g. `["results"]` |

---

## 10. Environment / server (admin panel, not per paper)

| Variable | Default | UI suggestion |
|----------|---------|---------------|
| `AUTOPAPER_MAX_CONCURRENT_RUNS` | `2` | Number input (admin) |
| `RESEARCH_FOLLOWUP_ROUNDS` | `1` | 0–2 |
| `RESEARCH_FOLLOWUP_MAX_TASKS` | `4` | 1–8 |
| `EDITOR_VALIDATOR_SCORE_THRESHOLD` | `70` | Slider 50–90 |
| `EDITOR_VALIDATOR_REWRITE_MAX_ATTEMPTS` | `2` | 0–3 |

---

## 11. Suggested frontend screens

### A. Submit (`SubmitPage`)

- Required: title, overview, methods, ieee_format  
- Optional: authors, affiliation, target_journal, images, **results** (textarea)  
- Advanced (collapsed): mismatch policy, ieee_format help text  

### B. Ingest preview (new — after step 04)

Load `GET /api/runs/{id}/artifact?file=04_final_standardized.json` (endpoint TBD) or poll execution folder.

| Section | Controls |
|---------|----------|
| Text blocks | Per-row **`citation_gap` toggle**, edit `technical_analysis` |
| Images | Gallery; show `readable`, `excluded`, `duplicate_of` |
| Mismatches | Table with **severity** select + `issue` text |
| Cross-refs | List + add with **relationship** select |
| Key claims | Editable tags (top-level + per block) |

Buttons: **Continue to research** | **Re-run ingest**

### C. Run detail (`RunDetailPage`)

- Status, log SSE, PDF download  
- Validation summary from `12_editor_validation/manifest.json`  
- Actions: **Resume editor**, **Editor only** (future)  

---

## 12. Minimal JSON example (execution_008 style)

```json
{
  "key_claims": ["Recording duration: 12 weeks chronic implantation", "..."],
  "text_blocks": [
    {
      "relative_path": "description/overview.md",
      "citation_gap": true,
      "linked_images": []
    },
    {
      "relative_path": "details/method_notes.txt",
      "citation_gap": true,
      "linked_images": []
    }
  ],
  "images": [],
  "mismatch_flags": [],
  "excluded_images": []
}
```

---

## 13. API gaps to implement for full UI parity

| Feature | Suggested endpoint |
|---------|-------------------|
| Read step 04 | `GET /api/runs/{id}/standardized` |
| Patch step 04 options | `PATCH /api/runs/{id}/standardized` |
| List mismatch policy on submit | `mismatch_policy: continue \| strict \| prompt` on `POST /api/runs` |
| Results textarea | `results` form field → `details/results.txt` |
| Re-run from step | `POST /api/runs/{id}/resume?from=research` |

---

## Related files

| Topic | Location |
|-------|----------|
| Input folder layout | `pipeline/input/README.md` |
| Results template | `pipeline/input/templates/details_results.example.txt` |
| Text parser `citation_gap` rule | `pipeline/input/prompts/gemini_text_parser/current.md` |
| Joiner mismatch severities | `pipeline/input/prompts/gemini_joiner/current.md` |
| OpenAPI | `http://localhost:8000/docs` |
