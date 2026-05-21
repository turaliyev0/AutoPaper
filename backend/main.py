"""AutoPaper — backend service.

Exposes the full AutoPaper pipeline as a REST + SSE API.
Also serves the built React frontend from ../frontend/dist/.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pipeline_runner import run_pipeline
from run_store import RunStatus, store

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parent      # AutoPaper/backend/
_PROJECT_ROOT = _BACKEND_DIR.parent                 # AutoPaper/
_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"
_UPLOADS_DIR = _PROJECT_ROOT / "output" / "_uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AutoPaper API",
    version="2.0.0",
    description="Full pipeline: paper input → research → IEEE manuscript → PDF",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health / config
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/config")
def config() -> dict:
    """Return static configuration the frontend needs."""
    return {
        "ieee_formats": ["journal", "conference"],
        "max_images": 10,
        "accepted_image_types": ["image/png", "image/jpeg", "image/webp"],
    }

# ---------------------------------------------------------------------------
# Runs — list / get / delete
# ---------------------------------------------------------------------------

@app.get("/api/runs")
def list_runs() -> list[dict]:
    return store.all()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run.to_dict()


@app.get("/api/runs/{run_id}/log")
def get_log(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return {"lines": run.log_lines}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status == RunStatus.RUNNING:
        raise HTTPException(409, "Cannot delete a running job")
    store.delete(run_id)
    return {"deleted": run_id}


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

@app.get("/api/runs/{run_id}/pdf")
def download_pdf(run_id: str) -> FileResponse:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if not run.pdf_path or not Path(run.pdf_path).is_file():
        raise HTTPException(404, "PDF not yet available")
    return FileResponse(
        path=run.pdf_path,
        media_type="application/pdf",
        filename=f"autopaper_{run_id}.pdf",
        headers={"Content-Disposition": f'inline; filename="autopaper_{run_id}.pdf"'},
    )


# ---------------------------------------------------------------------------
# SSE — live log stream
# ---------------------------------------------------------------------------

@app.get("/api/runs/{run_id}/stream")
async def stream_log(run_id: str) -> StreamingResponse:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")

    async def event_gen():
        q = run.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
        finally:
            run.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Start a run — upload only
# ---------------------------------------------------------------------------

@app.post("/api/runs", status_code=201)
async def start_run(
    background_tasks: BackgroundTasks,
    # Paper identity
    title: str = Form(..., description="Paper title"),
    authors: str = Form(default="", description="Author names, comma-separated"),
    affiliation: str = Form(default="", description="Institution / affiliation"),
    target_journal: str = Form(default="IEEE", description="Target journal"),
    # Content
    overview: str = Form(..., description="Paper overview / description / hypothesis"),
    methods: str = Form(default="", description="Experimental methods and parameters"),
    # Settings
    ieee_format: str = Form(default="journal", description="journal or conference"),
    # Files
    images: list[UploadFile] = File(default=[], description="Figure images (PNG/JPG)"),
) -> dict:
    """
    Submit a paper for full pipeline processing.

    Creates the standard AutoPaper folder layout from the uploaded content,
    then runs: paper_input → research (orchestrator + search) → editor → PDF.
    """
    if ieee_format not in ("journal", "conference"):
        raise HTTPException(422, "ieee_format must be 'journal' or 'conference'")

    # Build input folder
    folder_name = f"upload_{uuid.uuid4().hex[:10]}"
    input_path = _UPLOADS_DIR / folder_name
    for sub in ("description", "details", "images", "metadata"):
        (input_path / sub).mkdir(parents=True, exist_ok=True)

    # Write overview
    (input_path / "description" / "overview.md").write_text(
        f"# {title}\n\n{overview.strip()}",
        encoding="utf-8",
    )

    # Write method notes
    (input_path / "details" / "method_notes.txt").write_text(
        methods.strip() or "No method notes provided.",
        encoding="utf-8",
    )

    # Build author list
    author_list = [
        {"name": a.strip(), "affiliation": affiliation.strip(), "role": "Researcher"}
        for a in (authors.split(",") if authors.strip() else ["Author"])
        if a.strip()
    ]

    # paper_meta.json
    meta = {
        "project_title": title.strip(),
        "authors": author_list,
        "target_journal": target_journal.strip() or "IEEE",
        "manuscript_details": {
            "language": "en",
            "version": "1.0.0",
            "submission_track": "Original Research Article",
        },
    }
    (input_path / "metadata" / "paper_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save uploaded images
    saved_images: list[str] = []
    for img in images:
        if img.filename:
            safe_name = Path(img.filename).name
            dest = input_path / "images" / safe_name
            dest.write_bytes(await img.read())
            saved_images.append(safe_name)

    # Create run record
    run = store.create(
        paper_title=title.strip(),
        ieee_format=ieee_format,
    )

    background_tasks.add_task(run_pipeline, run, input_path, ieee_format=ieee_format)

    return {
        "run_id": run.run_id,
        "status": "pending",
        "paper_title": title,
        "images_saved": saved_images,
    }


# ---------------------------------------------------------------------------
# Serve React frontend (production build)
# ---------------------------------------------------------------------------

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def serve_spa(full_path: str = "") -> HTMLResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404)
        index = _FRONTEND_DIST / "index.html"
        if not index.is_file():
            return HTMLResponse("<h1>Frontend not built. Run: npm run build</h1>", 503)
        return HTMLResponse(index.read_text(encoding="utf-8"))
