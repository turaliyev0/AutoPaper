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

from backend.auth import UserPublic, get_current_user
from backend.db.run_store import RunStatus, store
from backend.runs import (
    MAX_CONCURRENT_RUNS,
    PipelineRunConfig,
    list_artifacts,
    read_artifact_json,
    resolve_artifact_file,
    run_pipeline,
    run_pipeline_continue,
)

router = APIRouter(prefix="/api", tags=["Runs"])

_SAFE_RE = re.compile(r"[^\w.\-]")
_UPLOADS_DIR = Path(__file__).resolve().parents[3] / "output" / "_uploads"
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


class InputGapsResponse(BaseModel):
    blocking: bool
    gaps: list[dict[str, str]]


class SupplementRequest(BaseModel):
    answers: dict[str, str] = Field(
        description="Map of gap id → user text (see GET /api/runs/{id}/input-gaps)",
    )


class SupplementResponse(BaseModel):
    ok: bool
    status: str
    message: str


class ResearchTaskSummary(BaseModel):
    slug: str
    index: int | None = None
    agent_id: str = ""
    task: str = ""
    success: bool = True
    verdict: str = ""
    coverage: str = ""
    overview: str = ""


class ResearchOverviewResponse(BaseModel):
    available: bool
    task_count: int = 0
    validation_pass: int = 0
    validation_warn: int = 0
    validation_fail: int = 0
    has_plan: bool = False
    has_index: bool = False
    main_topic: str = ""


class ResearchIndexResponse(BaseModel):
    markdown: str = ""
    meta: dict | None = None


class ResearchTaskDetailResponse(BaseModel):
    slug: str
    task: dict
    validation: dict | None = None


def _execution_dir(run) -> Path:
    if not run.execution_dir:
        raise HTTPException(404, "Execution directory not ready")
    root = Path(run.execution_dir)
    if not root.is_dir():
        raise HTTPException(404, "Execution directory not found")
    return root


def _research_available(root: Path) -> bool:
    return (root / "06_research" / "manifest.json").is_file()


def _merge_research_tasks(root: Path) -> list[dict]:
    research_manifest = read_artifact_json(str(root), "06_research/manifest.json")
    validation_manifest: dict = {}
    val_path = root / "07_validation" / "manifest.json"
    if val_path.is_file():
        validation_manifest = json.loads(val_path.read_text(encoding="utf-8"))

    val_by_slug = {
        str(v.get("slug") or ""): v
        for v in (validation_manifest.get("tasks") or [])
        if isinstance(v, dict)
    }

    merged: list[dict] = []
    for entry in research_manifest.get("tasks") or []:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "")
        val = val_by_slug.get(slug) or {}
        val_file = str(val.get("filename") or "")
        overview = ""
        if val_file:
            try:
                vdata = read_artifact_json(str(root), f"07_validation/{val_file}")
                overview = str(vdata.get("overview") or "")[:500]
            except HTTPException:
                overview = ""
        merged.append(
            {
                "slug": slug,
                "index": entry.get("index"),
                "agent_id": str(entry.get("agent_id") or val.get("agent_id") or ""),
                "task": str(entry.get("task") or "")[:300],
                "success": bool(entry.get("success", True)),
                "verdict": str(val.get("verdict") or ""),
                "coverage": str(val.get("coverage") or ""),
                "overview": overview,
                "research_file": str(entry.get("filename") or ""),
                "validation_file": val_file,
            }
        )
    return merged


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
    "/runs/{run_id}/input-gaps",
    response_model=InputGapsResponse,
    summary="Questions to answer when input is incomplete (status awaiting_input)",
)
def get_input_gaps(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    if not run.execution_dir:
        raise HTTPException(404, "Execution directory not ready")
    gaps_path = Path(run.execution_dir) / "04_input_gaps.json"
    if not gaps_path.is_file():
        raise HTTPException(404, "No input gaps file — run is not waiting for supplements")
    try:
        return json.loads(gaps_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Invalid gaps file: {exc}") from exc


@router.post(
    "/runs/{run_id}/supplement",
    response_model=SupplementResponse,
    summary="Submit answers for missing input and resume the pipeline",
)
async def submit_supplement(
    run_id: str,
    body: SupplementRequest,
    background_tasks: BackgroundTasks,
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    from pipeline.input.completeness_gate import load_gaps_file

    run = _get_run_or_404(run_id)
    if run.status != RunStatus.AWAITING_INPUT:
        raise HTTPException(
            409,
            f"Run is not awaiting input (status={run.status.value})",
        )
    if not run.execution_dir:
        raise HTTPException(409, "Execution directory unknown")

    execution_dir = Path(run.execution_dir)
    gaps_report = load_gaps_file(execution_dir)
    if gaps_report is None:
        raise HTTPException(404, "04_input_gaps.json not found")

    missing = [
        g.id
        for g in gaps_report.gaps
        if g.severity == "required" and not str(body.answers.get(g.id) or "").strip()
    ]
    if missing:
        raise HTTPException(
            422,
            f"Missing required answers for: {', '.join(missing)}",
        )

    input_path = Path(run.input_path) if run.input_path else None
    if input_path is None or not input_path.is_dir():
        from pipeline.input.resume_input import input_root_from_manifest

        input_path = input_root_from_manifest(execution_dir)
    if input_path is None or not input_path.is_dir():
        raise HTTPException(409, "Original upload folder not found; cannot apply supplements")

    supplement_path = execution_dir / "04_supplement_answers.json"
    supplement_path.write_text(
        json.dumps({"answers": body.answers}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    pipe_cfg = PipelineRunConfig(
        full_research=True,
        ieee_edit=True,
        log_editor=True,
        ingest_only=False,
        mismatch_policy="continue",
        completeness_policy="auto",
    )

    background_tasks.add_task(
        run_pipeline_continue,
        run,
        input_path,
        execution_dir,
        ieee_format=run.ieee_format,
        config=pipe_cfg,
        supplement_json=supplement_path,
    )

    return {
        "ok": True,
        "status": "running",
        "message": "Supplements accepted; pipeline resuming from research stage.",
    }


@router.get(
    "/runs/{run_id}/research",
    response_model=ResearchOverviewResponse,
    summary="Research stage overview (tasks, validation counts, plan topic)",
)
def get_research_overview(
    run_id: str,
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    run = _get_run_or_404(run_id)
    root = _execution_dir(run)
    if not _research_available(root):
        return ResearchOverviewResponse(available=False).model_dump()

    plan: dict = {}
    plan_path = root / "05_orchestrator_plan.json"
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))

    tasks = _merge_research_tasks(root)
    v_pass = sum(1 for t in tasks if t.get("verdict") == "pass")
    v_warn = sum(1 for t in tasks if t.get("verdict") == "warn")
    v_fail = sum(1 for t in tasks if t.get("verdict") == "fail")

    return ResearchOverviewResponse(
        available=True,
        task_count=len(tasks),
        validation_pass=v_pass,
        validation_warn=v_warn,
        validation_fail=v_fail,
        has_plan=plan_path.is_file(),
        has_index=(root / "08_research_index.md").is_file(),
        main_topic=str((plan.get("research_goal") or {}).get("main_topic") or plan.get("main_topic") or ""),
    ).model_dump()


@router.get("/runs/{run_id}/research/plan", summary="05_orchestrator_plan.json")
def get_research_plan(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    return read_artifact_json(run.execution_dir, "05_orchestrator_plan.json")


@router.get(
    "/runs/{run_id}/research/index",
    response_model=ResearchIndexResponse,
    summary="08_research_index.md catalog (+ optional meta JSON)",
)
def get_research_index(
    run_id: str,
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    run = _get_run_or_404(run_id)
    root = _execution_dir(run)
    index_path = root / "08_research_index.md"
    if not index_path.is_file():
        raise HTTPException(404, "08_research_index.md not available yet")
    markdown = index_path.read_text(encoding="utf-8")
    meta = None
    meta_path = root / "08_research_index.meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {"markdown": markdown, "meta": meta}


@router.get(
    "/runs/{run_id}/research/tasks",
    response_model=list[ResearchTaskSummary],
    summary="List research tasks merged with validation verdicts",
)
def list_research_tasks(
    run_id: str,
    _user: UserPublic = Depends(get_current_user),
) -> list[dict]:
    run = _get_run_or_404(run_id)
    root = _execution_dir(run)
    if not _research_available(root):
        raise HTTPException(404, "Research stage not available yet")
    return _merge_research_tasks(root)


@router.get(
    "/runs/{run_id}/research/tasks/{slug}",
    response_model=ResearchTaskDetailResponse,
    summary="One research task JSON plus its validation record",
)
def get_research_task(
    run_id: str,
    slug: str,
    _user: UserPublic = Depends(get_current_user),
) -> dict:
    run = _get_run_or_404(run_id)
    root = _execution_dir(run)
    if not _research_available(root):
        raise HTTPException(404, "Research stage not available yet")

    research_manifest = read_artifact_json(str(root), "06_research/manifest.json")
    match = None
    for entry in research_manifest.get("tasks") or []:
        if isinstance(entry, dict) and str(entry.get("slug") or "") == slug:
            match = entry
            break
    if match is None:
        raise HTTPException(404, f"Research task not found: {slug}")

    task_file = str(match.get("filename") or "")
    task_data = read_artifact_json(str(root), f"06_research/{task_file}")

    validation_data = None
    val_path = root / "07_validation" / f"{slug}.validation.json"
    if not val_path.is_file():
        for entry in (read_artifact_json(str(root), "07_validation/manifest.json").get("tasks") or []):
            if isinstance(entry, dict) and str(entry.get("slug") or "") == slug:
                vf = str(entry.get("filename") or "")
                if vf:
                    validation_data = read_artifact_json(str(root), f"07_validation/{vf}")
                break
    else:
        validation_data = json.loads(val_path.read_text(encoding="utf-8"))

    return {
        "slug": slug,
        "task": task_data,
        "validation": validation_data,
    }


@router.get(
    "/runs/{run_id}/manuscript-qa",
    summary="Holistic editor QA report (12_editor_validation/manuscript_qa_report.json)",
)
def get_manuscript_qa(run_id: str, _user: UserPublic = Depends(get_current_user)) -> dict:
    run = _get_run_or_404(run_id)
    return read_artifact_json(
        run.execution_dir,
        "12_editor_validation/manuscript_qa_report.json",
    )


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
        completeness_policy="auto",
    )

    run = store.create(paper_title=title.strip(), ieee_format=ieee_format)
    run.input_path = str(input_path.resolve())
    store.persist(run)
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
