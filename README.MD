# AutoPaper

Converts raw research data into a peer-review-ready IEEE manuscript using a multi-agent AI pipeline.

---

## Architecture

```
AutoPaper/
├── backend/              # FastAPI service — REST + SSE API
│   ├── api/routes/       # auth, runs, system HTTP handlers
│   ├── auth/             # Google OAuth + session tokens
│   ├── db/               # Run registry (output/_runs/, SSE pub/sub)
│   ├── runs/             # Pipeline subprocess runner + artifacts
│   ├── logging/          # LLM traces, editor_run.log helpers
│   └── requirements.txt
│
├── frontend/             # React / Vite standalone app
│   ├── src/
│   │   ├── api/client.ts # Typed API client (reads VITE_API_URL)
│   │   └── pages/        # RunsPage, SubmitPage, RunDetailPage
│   ├── .env              # VITE_API_URL=http://localhost:8000
│   └── .env.example
│
├── pipeline/             # All pipeline stages
│   ├── input/            # Stage 1 — ingest, clean, image analysis
│   ├── research/         # Stage 2 — AI orchestrator + grounded search
│   └── editor/           # Stage 3 — IEEE LaTeX authoring + PDF
│
├── src/autopaper/main/   # CLI entry point (`autopaper` command)
├── output/               # Generated manuscripts (gitignored)
├── start.ps1             # Single-command startup (Windows / PowerShell)
├── pyproject.toml
└── requirements.txt
```

### Pipeline stages

| # | Stage | Output |
|---|-------|--------|
| 1 | `pipeline.input` — parse text, vision-describe images, join | `01–04_*.json` |
| 2 | `pipeline.research` — orchestrator plans tasks → parallel search → validate → index | `05–08_*.json/md` |
| 3 | `pipeline.editor` — plan sections, write LaTeX, generate figures, validate, compile PDF | `09–13_*/` |

---

## Quick start

### 1. Environment

Copy `.env.example` to `.env` and fill in your API keys:

```env
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
```

### 2. Start (production)

```powershell
.\start.ps1
```

Opens at **http://localhost:8000** — backend serves both the API and the compiled UI.

### 3. Start (dev — hot-reload frontend)

```powershell
.\start.ps1 -Dev
# API:      http://localhost:8000
# Frontend: http://localhost:5173
```

### API dev server (safe reload)

Do **not** use `uvicorn main:app --reload` alone — the pipeline writes files under `output/`, which triggers a reload and clears in-memory run IDs.

```powershell
python run_dev.py
```

`run_dev.py` sets `reload_dirs` to `backend/`, `src/`, and `pipeline/` only — **not** `output/`. Figure generation writes `.py` files under `output/execution_NNN/11_figures/`; watching that tree with plain `--reload` kills long runs.

Run metadata and logs are persisted under `output/_runs/{run_id}.json` and `.log` so `GET /api/runs/{id}` survives restarts.

For long pipeline runs, prefer **no reload**:

```powershell
python run_stable.py
# or: uvicorn main:app --host 0.0.0.0 --port 8000
```

Resume a stuck editor run (reuses plan + sections, continues figures):

```powershell
python -m autopaper.main.app --editor-only --editor-resume --execution-dir output/execution_001 --log-editor
```

---

## API

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | **Swagger UI** — interactive API explorer |
| http://localhost:8000/redoc | ReDoc — alternative API reference |
| http://localhost:8000/openapi.json | Raw OpenAPI 3.1 schema |

### Endpoints at a glance

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/health` | Health check |
| `GET`  | `/api/config` | Frontend config (formats, limits) |
| `GET`  | `/api/runs` | List all runs |
| `POST` | `/api/runs` | **Submit paper → start pipeline** |
| `GET`  | `/api/runs/{id}` | Run status + stats |
| `DELETE` | `/api/runs/{id}` | Delete a finished run |
| `GET`  | `/api/runs/{id}/log` | Full log snapshot |
| `GET`  | `/api/runs/{id}/stream` | SSE live log stream |
| `GET`  | `/api/runs/{id}/pdf` | Download / preview PDF |

### Submit a run — `POST /api/runs`

`multipart/form-data` fields:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `title` | ✓ | string | Paper title |
| `overview` | ✓ | string | Research narrative, introduction, hypothesis |
| `authors` | | string | Comma-separated author names |
| `affiliation` | | string | Institution |
| `target_journal` | | string | Target journal (default: `IEEE`) |
| `methods` | | string | Experimental methods and parameters |
| `ieee_format` | | string | `journal` (default) or `conference` |
| `images` | | files | Figure images — PNG / JPG / WebP, max 10 |

**Response `201`:**
```json
{
  "run_id":       "a1b2c3d4",
  "status":       "pending",
  "paper_title":  "My Paper Title",
  "images_saved": ["fig1.png", "fig2.png"]
}
```

### SSE stream — `GET /api/runs/{id}/stream`

Connect with `EventSource`. Events:

```
data: {"type": "log",    "line": "[Step 2] research: launching…"}
data: {"type": "status", "status": "running"}
data: {"type": "done",   "status": "done"}
```

JavaScript example:
```js
const es = new EventSource(`/api/runs/${runId}/stream`);
es.onmessage = ({ data }) => {
  const event = JSON.parse(data);
  if (event.type === "log")  console.log(event.line);
  if (event.type === "done") es.close();
};
```

---

## Deploy frontend separately

The frontend is a standalone Vite app. Point it at any backend:

```powershell
cd frontend
$env:VITE_API_URL = "https://api.example.com"
npm run build
# Serve dist/ with any static host (Netlify, Vercel, nginx)
```

---

## Configuration reference (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✓ | OpenAI API key (research + editor orchestrators) |
| `GOOGLE_API_KEY` | ✓ | Google / Gemini API key (search, validator, editor) |
| `ANTHROPIC_API_KEY` | | Claude key (reserved; `claude_search` agent is disabled in this build) |
| `EDITOR_IEEE_FORMAT` | | Default output format: `journal` or `conference` |
| `EDITOR_ORCHESTRATOR_MODEL` | | OpenAI model for editor orchestrator (default: `gpt-4o`) |
| `EDITOR_SECTION_WRITER_MODEL` | | Gemini model for section writer (default: `gemini-2.5-flash`) |
| `EDITOR_VALIDATOR_MODEL` | | Gemini model for IEEE validator (default: `gemini-2.5-flash`) |
| `RESEARCH_ORCHESTRATOR_MODEL` | | OpenAI model for research orchestrator (default: `gpt-4o`) |
| `RESEARCH_GEMINI_SEARCH_MODEL` | | Gemini model for search agent (default: `gemini-2.0-flash`) |
