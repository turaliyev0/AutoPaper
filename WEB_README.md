# AutoPaper Web

Full-stack interface for the AutoPaper pipeline.  
Upload your research data → get a publication-ready IEEE manuscript.

---

## Quick Start

```powershell
# From this directory (autopaper_web/)
.\start.ps1
```

Opens at **http://localhost:8000** — the backend also serves the compiled frontend.

### Dev mode (hot-reload UI)

```powershell
.\start.ps1 -Dev
```

- Frontend dev server: http://localhost:5173  
- Backend API: http://localhost:8000

---

## Architecture

```
AutoPaper/                  ← Core pipeline (Python)
  paper_input/              ← Stage 1: ingest & clean
  research/                 ← Stage 2: AI research orchestrator
  editor/                   ← Stage 3: IEEE editor + PDF
  output/                   ← Generated manuscripts
    _uploads/               ← Web-submitted papers

autopaper_web/              ← Full-stack web interface
  backend/                  ← FastAPI service
    main.py                 ← REST API + SSE + static file serving
    pipeline_runner.py      ← Subprocess runner for the pipeline
    run_store.py            ← In-memory run registry
    requirements.txt
  frontend/                 ← Standalone React / Vite app
    src/
      api/client.ts         ← Typed API client (reads VITE_API_URL)
      pages/
        RunsPage            ← Dashboard of all runs
        SubmitPage          ← Upload form
        RunDetailPage       ← Live log + PDF viewer
    .env                    ← VITE_API_URL (default: localhost:8000)
    .env.example
  start.ps1                 ← Single-command startup
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET    | /api/health | Health check |
| GET    | /api/config | Frontend config (formats, limits) |
| GET    | /api/runs | List all runs |
| POST   | /api/runs | **Start a new run** (multipart form) |
| GET    | /api/runs/{id} | Run details |
| DELETE | /api/runs/{id} | Delete a finished run |
| GET    | /api/runs/{id}/log | Full log snapshot |
| GET    | /api/runs/{id}/stream | SSE live log stream |
| GET    | /api/runs/{id}/pdf | Download / preview PDF |

### POST /api/runs — form fields

| Field | Required | Description |
|-------|----------|-------------|
| `title` | ✓ | Paper title |
| `overview` | ✓ | Research narrative / description |
| `authors` | | Comma-separated author names |
| `affiliation` | | Institution |
| `target_journal` | | Target journal name |
| `methods` | | Experimental method notes |
| `ieee_format` | | `journal` (default) or `conference` |
| `images` | | Image files (PNG/JPG, multiple) |

---

## Deploying the frontend separately

The frontend is a standalone Vite app.  
Set `VITE_API_URL` before building:

```powershell
cd frontend
$env:VITE_API_URL = "https://your-api-server.com"
npm run build
# Serve the dist/ folder with any static host (Netlify, Vercel, nginx…)
```
