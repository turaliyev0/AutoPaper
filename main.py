"""AutoPaper — backend service.

Full REST + SSE API that drives the AutoPaper pipeline.
Swagger UI:   http://localhost:8000/docs
ReDoc:        http://localhost:8000/redoc
OpenAPI JSON: http://localhost:8000/openapi.json

When the React frontend is built (frontend/dist/), this server also
serves it as a single-page app on all non-API paths.
"""

from __future__ import annotations

import asyncio
import sys

# Windows: uvicorn may use SelectorEventLoop, which cannot spawn subprocesses.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import sys

# Windows: SelectorEventLoop cannot run subprocesses (NotImplementedError).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.pipeline_runner import MAX_CONCURRENT_RUNS, run_pipeline
from backend.run_store import RunStatus, store

_SAFE_RE = re.compile(r"[^\w.\-]")   # keep word chars, dots, hyphens


def _safe_filename(original: str, index: int) -> str:
    """Return a safe, short filename that won't exceed Windows MAX_PATH."""
    stem = Path(original).stem
    suffix = Path(original).suffix.lower() or ".jpg"
    # Keep only safe characters, collapse runs of underscores
    stem = _SAFE_RE.sub("_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    # Truncate stem so total filename stays under 60 chars
    max_stem = 50 - len(suffix)
    if len(stem) > max_stem or len(stem) == 0:
        stem = f"image_{index:02d}"
    return f"{stem}{suffix}"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT  = Path(__file__).resolve().parent     # AutoPaper/
_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"
_UPLOADS_DIR   = _PROJECT_ROOT / "output" / "_uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class RunSummary(BaseModel):
    """Summary of a pipeline run (returned by list and get endpoints)."""
    run_id:           str   = Field(description="Short hex run identifier")
    paper_title:      str   = Field(description="Title provided at submission")
    ieee_format:      str   = Field(description="'journal' or 'conference'")
    created_at:       str   = Field(description="ISO-8601 UTC timestamp")
    status:           str   = Field(description="pending | running | done | error")
    current_step:     str   = Field(description="Latest [STEP] message from the running pipeline")
    execution_dir:    str   = Field(description="Absolute path to output execution folder")
    has_pdf:          bool  = Field(description="True when main.pdf exists and is readable")
    error:            str   = Field(description="Error message if status == error, else empty")
    sections_ok:      int   = Field(description="Sections that passed IEEE validation")
    sections_total:   int   = Field(description="Total sections generated")
    validation_pass:  int   = Field(description="Sections with verdict = pass")
    validation_warn:  int   = Field(description="Sections with verdict = warn")
    validation_fail:  int   = Field(description="Sections with verdict = fail")

    model_config = {"json_schema_extra": {"example": {
        "run_id":         "a1b2c3d4",
        "paper_title":    "Chronic Neural Interface Stability",
        "ieee_format":    "journal",
        "created_at":     "2026-05-21T08:00:00Z",
        "status":         "done",
        "execution_dir":  "/path/to/output/execution_001",
        "has_pdf":        True,
        "error":          "",
        "sections_ok":    8, "sections_total": 8,
        "validation_pass": 7, "validation_warn": 1, "validation_fail": 0,
    }}}


class LogResponse(BaseModel):
    lines: list[str] = Field(description="Full log lines captured from the pipeline subprocess")

    model_config = {"json_schema_extra": {"example": {
        "lines": [
            "[AutoPaper] Starting pipeline for: My Paper",
            "[Step 1] paper_input: ingesting files…",
            "[Step 2] research: launching orchestrator…",
            "[AutoPaper] ✓ Pipeline completed successfully.",
        ]
    }}}


class StartRunResponse(BaseModel):
    run_id:        str       = Field(description="Unique run identifier — use for polling and SSE")
    status:        str       = Field(description="Always 'pending' immediately after submission")
    paper_title:   str       = Field(description="Paper title as accepted")
    images_saved:  list[str] = Field(description="Filenames of uploaded images")

    model_config = {"json_schema_extra": {"example": {
        "run_id":       "a1b2c3d4",
        "status":       "pending",
        "paper_title":  "Chronic Neural Interface Stability",
        "images_saved": ["fig1_snr.png", "fig2_array.png"],
    }}}


class DeleteResponse(BaseModel):
    deleted: str = Field(description="run_id that was removed")


class HealthResponse(BaseModel):
    status:  str = Field(description="Always 'ok'")
    version: str = Field(description="API version string")


class ConfigResponse(BaseModel):
    ieee_formats:           list[str]      = Field(description="Accepted values for ieee_format")
    max_images:             int            = Field(description="Maximum number of images per submission")
    accepted_image_types:   list[str]      = Field(description="Accepted MIME types for image uploads")
    max_concurrent_runs:    int            = Field(description="Max pipelines running at the same time")
    run_counts:             dict[str, int] = Field(description="Current run counts by status")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AutoPaper API",
    version="2.0.0",
    description=(
        "Converts raw research data (description, methods, images) into a "
        "peer-review-ready IEEE manuscript using a multi-agent AI pipeline.\n\n"
        "**Pipeline stages** (all run server-side):\n"
        "1. `paper_input` — ingest & clean uploaded files\n"
        "2. `research` — AI orchestrator + grounded search agents\n"
        "3. `editor` — IEEE-compliant LaTeX authoring + PDF compile\n\n"
        "Monitor progress in real-time via the **SSE stream** (`/api/runs/{id}/stream`)."
    ),
    contact={"name": "AutoPaper"},
    license_info={"name": "MIT"},
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

@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["System"],
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="2.0.0")


@app.get(
    "/api/config",
    response_model=ConfigResponse,
    summary="Frontend configuration",
    description="Returns static settings the frontend needs at startup (valid formats, upload limits).",
    tags=["System"],
)
def config() -> ConfigResponse:
    return ConfigResponse(
        ieee_formats=["journal", "conference"],
        max_images=10,
        accepted_image_types=["image/png", "image/jpeg", "image/webp"],
        max_concurrent_runs=MAX_CONCURRENT_RUNS,
        run_counts=store.counts(),
    )

# ---------------------------------------------------------------------------
# Runs — list / get / delete
# ---------------------------------------------------------------------------

@app.get(
    "/api/runs",
    response_model=list[RunSummary],
    summary="List all runs",
    description="Returns all submitted pipeline runs, newest first.",
    tags=["Runs"],
)
def list_runs() -> list[dict]:
    return store.all()


@app.get(
    "/api/runs/{run_id}",
    response_model=RunSummary,
    summary="Get run details",
    tags=["Runs"],
    responses={404: {"description": "Run not found"}},
)
def get_run(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run.to_dict()


@app.get(
    "/api/runs/{run_id}/log",
    response_model=LogResponse,
    summary="Get full log",
    description="Returns all captured log lines as a snapshot. Use the SSE stream for live output.",
    tags=["Runs"],
    responses={404: {"description": "Run not found"}},
)
def get_log(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return {"lines": run.log_lines}


@app.delete(
    "/api/runs/{run_id}",
    response_model=DeleteResponse,
    summary="Delete a run",
    description="Removes a finished run from the registry. Cannot delete a run that is still running.",
    tags=["Runs"],
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is still running"},
    },
)
def delete_run(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status in (RunStatus.RUNNING, RunStatus.QUEUED):
        raise HTTPException(409, "Cannot delete a running or queued job")
    store.delete(run_id)
    return {"deleted": run_id}

# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

@app.get(
    "/api/runs/{run_id}/pdf",
    summary="Download / preview PDF",
    description=(
        "Streams the compiled manuscript PDF.\n\n"
        "The `Content-Disposition` header is set to `inline` so browsers open "
        "the PDF directly; download it by saving from the browser."
    ),
    tags=["Runs"],
    responses={
        200: {"content": {"application/pdf": {}}, "description": "IEEE manuscript PDF"},
        404: {"description": "Run not found or PDF not yet available"},
    },
)
def download_pdf(run_id: str) -> FileResponse:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if not run.pdf_path or not Path(run.pdf_path).is_file():
        raise HTTPException(404, "PDF not yet available — run must complete first")
    return FileResponse(
        path=run.pdf_path,
        media_type="application/pdf",
        filename=f"autopaper_{run_id}.pdf",
        headers={"Content-Disposition": f'inline; filename="autopaper_{run_id}.pdf"'},
    )

# ---------------------------------------------------------------------------
# SSE — live log stream
# ---------------------------------------------------------------------------

@app.get(
    "/api/runs/{run_id}/stream",
    summary="Live log stream (SSE)",
    description=(
        "Server-Sent Events stream of pipeline log lines.\n\n"
        "**Event types:**\n"
        "- `data: {\"type\": \"log\", \"line\": \"...\"}` — one log line\n"
        "- `data: {\"type\": \"status\", \"status\": \"running\"}` — status change\n"
        "- `data: {\"type\": \"done\", \"status\": \"done|error\"}` — stream closed\n\n"
        "The stream also sends `: ping` keep-alive comments every 30 s."
    ),
    tags=["Runs"],
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE stream"},
        404: {"description": "Run not found"},
    },
)
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
# Submit a new run
# ---------------------------------------------------------------------------

@app.post(
    "/api/runs",
    response_model=StartRunResponse,
    status_code=201,
    summary="Submit a paper for processing",
    description=(
        "Upload your research data to kick off the full AutoPaper pipeline.\n\n"
        "The pipeline runs asynchronously in the background:\n"
        "1. **paper_input** — parses and cleans your text and images\n"
        "2. **research** — multi-agent grounded literature search\n"
        "3. **editor** — IEEE-compliant LaTeX authoring + PDF compilation\n\n"
        "Poll `GET /api/runs/{run_id}` or subscribe to `GET /api/runs/{run_id}/stream` "
        "to track progress. The PDF is available at `GET /api/runs/{run_id}/pdf` once "
        "`status == done`."
    ),
    tags=["Runs"],
    responses={
        201: {"description": "Run accepted, processing started"},
        422: {"description": "Validation error (e.g. invalid ieee_format)"},
    },
)
async def start_run(
    background_tasks: BackgroundTasks,
    title: Annotated[str, Form(description="Paper title (required)")],
    overview: Annotated[str, Form(description="Research narrative — introduction, hypothesis, background (required)")],
    authors: Annotated[str, Form(description="Author names, comma-separated")] = "",
    affiliation: Annotated[str, Form(description="Institution / affiliation")] = "",
    target_journal: Annotated[str, Form(description="Target journal name")] = "IEEE",
    methods: Annotated[str, Form(description="Experimental methods, parameters, materials")] = "",
    ieee_format: Annotated[str, Form(description="Output format: 'journal' or 'conference'")] = "journal",
    images: Annotated[list[UploadFile], File(description="Figure images (PNG / JPG / WebP, max 10)")] = [],
) -> dict:
    if ieee_format not in ("journal", "conference"):
        raise HTTPException(422, "ieee_format must be 'journal' or 'conference'")

    # Build the input folder AutoPaper expects
    folder_name = f"upload_{uuid.uuid4().hex[:10]}"
    input_path  = _UPLOADS_DIR / folder_name
    for sub in ("description", "details", "images", "metadata"):
        (input_path / sub).mkdir(parents=True, exist_ok=True)

    (input_path / "description" / "overview.md").write_text(
        f"# {title}\n\n{overview.strip()}", encoding="utf-8"
    )
    (input_path / "details" / "method_notes.txt").write_text(
        methods.strip() or "No method notes provided.", encoding="utf-8"
    )

    author_list = [
        {"name": a.strip(), "affiliation": affiliation.strip(), "role": "Researcher"}
        for a in (authors.split(",") if authors.strip() else ["Author"])
        if a.strip()
    ]
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
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    saved_images: list[str] = []
    for idx, img in enumerate(images, 1):
        if img.filename:
            safe_name = _safe_filename(img.filename, idx)
            dest = input_path / "images" / safe_name
            dest.write_bytes(await img.read())
            saved_images.append(safe_name)

    run = store.create(paper_title=title.strip(), ieee_format=ieee_format)
    background_tasks.add_task(run_pipeline, run, input_path, ieee_format=ieee_format)

    return {
        "run_id":       run.run_id,
        "status":       "pending",
        "paper_title":  title.strip(),
        "images_saved": saved_images,
    }

# ---------------------------------------------------------------------------
# Serve built React frontend (production)
# ---------------------------------------------------------------------------

if _FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    @app.get(
        "/{full_path:path}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def serve_spa(full_path: str = "") -> HTMLResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404)
        index = _FRONTEND_DIST / "index.html"
        if not index.is_file():
            return HTMLResponse("<h1>Frontend not built. Run: npm run build</h1>", 503)
        return HTMLResponse(index.read_text(encoding="utf-8"))
