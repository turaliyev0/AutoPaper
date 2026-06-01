"""Pipeline run endpoints (protected except where noted)."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.artifacts import list_artifacts, read_artifact_json, resolve_artifact_file
from backend.auth import UserPublic, auth_disabled, get_current_user
from backend.pipeline_runner import MAX_CONCURRENT_RUNS, PipelineRunConfig, run_pipeline
from backend.run_store import RunStatus, store

router = APIRouter(prefix="/api", tags=["Runs"])

_SAFE_RE = re.compile(r"[^\w.\-]")
_UPLOADS_DIR = Path(__file__).resolve().parents[2] / "output" / "_uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _form_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")


def _standardized_path(run) -> Path | None:
    if not run.execution_dir:
        return None
    path = Path(run.execution_dir) / "04_final_standardized.json"
    return path if path.is_file() else None


def _safe_filename(original: str, index: int) -> str:
    stem = Path(original).stem
    suffix = Path(original).suffix.lower() or ".jpg"
    stem = _SAFE_RE.sub("_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    max_stem = 50 - len(suffix)
    if len(stem) > max_stem or len(stem) == 0:
        stem = f"image_{index:02d}"
    return f"{stem}{suffix}"


def _get_run_or_404(run_id: str):
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


class RunSummary(BaseModel):
    run_id: str
    paper_title: str
    ieee_format: str
    created_at: str
    status: str
    current_step: str
    execution_dir: str
    has_pdf: bool
    error: str
    sections_ok: int
    sections_total: int
    validation_pass: int
    validation_warn: int
    validation_fail: int


class LogResponse(BaseModel):
    lines: list[str]


class StartRunResponse(BaseModel):
    run_id: str
    status: str
    paper_title: str
    images_saved: list[str]


class DeleteResponse(BaseModel):
    deleted: str


class ArtifactListResponse(BaseModel):
    artifacts: list[dict[str, str | int]]


class PatchOk(BaseModel):
    ok: bool
    path: str


@router.get("/runs", response_model=list[RunSummary], summary="List all runs")
def list_runs(_user: UserPublic = Depends(get_current_user)) -> list[dict]:
    return store.all()


@router.get("/runs/{run_id}", response_model=RunSummary, summary="Get run details")
def get_run(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    return _get_run_or_404(run_id).to_dict()


@router.get("/runs/{run_id}/log", response_model=LogResponse, summary="Full log snapshot")
def get_log(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    return {"lines": run.log_lines}


@router.delete("/runs/{run_id}", response_model=DeleteResponse, summary="Delete a finished run")
def delete_run(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    if run.status in (RunStatus.RUNNING, RunStatus.QUEUED):
        raise HTTPException(409, "Cannot delete a running or queued job")
    store.delete(run_id)
    return {"deleted": run_id}


@router.get("/runs/{run_id}/pdf", summary="Download / preview PDF")
def download_pdf(run_id: str, _user: UserPublic = Depends(get_current_user)) -> FileResponse:
    run = _get_run_or_404(run_id)
    if not run.pdf_path or not Path(run.pdf_path).is_file():
        raise HTTPException(404, "PDF not yet available — run must complete first")
    return FileResponse(
        path=run.pdf_path,
        media_type="application/pdf",
        filename=f"autopaper_{run_id}.pdf",
        headers={"Content-Disposition": f'inline; filename="autopaper_{run_id}.pdf"'},
    )


@router.get("/runs/{run_id}/stream", summary="Live log stream (SSE)")
async def stream_log(
    run_id: str,
    _user: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    run = _get_run_or_404(run_id)

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


@router.get("/runs/{run_id}/standardized", summary="Get 04_final_standardized.json")
def get_standardized(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    path = _standardized_path(run)
    if path is None:
        raise HTTPException(404, "04_final_standardized.json not available yet")
    return json.loads(path.read_text(encoding="utf-8"))


@router.patch("/runs/{run_id}/standardized", response_model=PatchOk, summary="Update step 04 JSON")
def patch_standardized(
    run_id: str,
    body: dict,
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    run = _get_run_or_404(run_id)
    path = _standardized_path(run)
    if path is None:
        raise HTTPException(404, "04_final_standardized.json not available yet")
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "path": str(path)}


@router.get(
    "/runs/{run_id}/artifacts",
    response_model=ArtifactListResponse,
    summary="List downloadable execution artifacts",
)
def get_artifact_list(
    run_id: str,
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    run = _get_run_or_404(run_id)
    if not run.execution_dir:
        raise HTTPException(404, "Execution directory not ready")
    return {"artifacts": list_artifacts(run.execution_dir)}


@router.get(
    "/runs/{run_id}/artifacts/{artifact_path:path}",
    summary="Download one artifact file",
)
def get_artifact_file(
    run_id: str,
    artifact_path: str,
    _user: UserPublic = Depends(get_current_user),
) -> FileResponse:
    run = _get_run_or_404(run_id)
    full = resolve_artifact_file(run.execution_dir, artifact_path)
    media = "application/octet-stream"
    if full.suffix == ".json":
        media = "application/json"
    elif full.suffix == ".md":
        media = "text/markdown; charset=utf-8"
    elif full.suffix == ".tex":
        media = "text/plain; charset=utf-8"
    elif full.suffix == ".pdf":
        media = "application/pdf"
    elif full.suffix == ".log":
        media = "text/plain; charset=utf-8"
    return FileResponse(path=full, media_type=media, filename=full.name)


@router.get("/runs/{run_id}/validation", summary="Editor validation manifest + results")
def get_validation(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    manifest = read_artifact_json(run.execution_dir, "12_editor_validation/manifest.json")
    return manifest


@router.get("/runs/{run_id}/editor-plan", summary="09_editor_plan.json")
def get_editor_plan(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    return read_artifact_json(run.execution_dir, "09_editor_plan.json")


@router.get("/runs/{run_id}/sections", summary="10_sections manifest")
def get_sections_manifest(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    return read_artifact_json(run.execution_dir, "10_sections/manifest.json")


@router.post("/runs", response_model=StartRunResponse, status_code=201, summary="Submit a new run")
async def start_run(
    background_tasks: BackgroundTasks,
    title: Annotated[str, Form(description="Paper title")],
    overview: Annotated[str, Form(description="Research narrative")],
    authors: Annotated[str, Form()] = "",
    affiliation: Annotated[str, Form()] = "",
    target_journal: Annotated[str, Form()] = "IEEE",
    methods: Annotated[str, Form()] = "",
    results: Annotated[str, Form(description="Measured outcomes → details/results.txt")] = "",
    ieee_format: Annotated[str, Form()] = "journal",
    images: Annotated[list[UploadFile], File()] = [],
    full_research: Annotated[str, Form()] = "true",
    ieee_edit: Annotated[str, Form()] = "true",
    log_editor: Annotated[str, Form()] = "true",
    ingest_only: Annotated[str, Form()] = "false",
    mismatch_policy: Annotated[str, Form()] = "continue",
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    if ieee_format not in ("journal", "conference"):
        raise HTTPException(422, "ieee_format must be 'journal' or 'conference'")
    if mismatch_policy not in ("continue", "strict", "prompt"):
        raise HTTPException(422, "mismatch_policy must be 'continue', 'strict', or 'prompt'")

    folder_name = f"upload_{uuid.uuid4().hex[:10]}"
    input_path = _UPLOADS_DIR / folder_name
    for sub in ("description", "details", "images", "metadata"):
        (input_path / sub).mkdir(parents=True, exist_ok=True)

    (input_path / "description" / "overview.md").write_text(
        f"# {title}\n\n{overview.strip()}",
        encoding="utf-8",
    )
    (input_path / "details" / "method_notes.txt").write_text(
        methods.strip() or "No method notes provided.",
        encoding="utf-8",
    )
    if results.strip():
        (input_path / "details" / "results.txt").write_text(results.strip(), encoding="utf-8")

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
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    saved_images: list[str] = []
    for idx, img in enumerate(images, 1):
        if img.filename:
            safe_name = _safe_filename(img.filename, idx)
            dest = input_path / "images" / safe_name
            dest.write_bytes(await img.read())
            saved_images.append(safe_name)

    pipe_cfg = PipelineRunConfig(
        full_research=_form_bool(full_research),
        ieee_edit=_form_bool(ieee_edit),
        log_editor=_form_bool(log_editor),
        ingest_only=_form_bool(ingest_only),
        mismatch_policy="continue" if mismatch_policy == "prompt" else mismatch_policy,
    )

    run = store.create(paper_title=title.strip(), ieee_format=ieee_format)
    background_tasks.add_task(
        run_pipeline,
        run,
        input_path,
        ieee_format=ieee_format,
        config=pipe_cfg,
    )

    return {
        "run_id": run.run_id,
        "status": "pending",
        "paper_title": title.strip(),
        "images_saved": saved_images,
    }
