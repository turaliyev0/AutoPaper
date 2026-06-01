"""Public system endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.auth import UserPublic, auth_disabled, get_current_user
from backend.pipeline_runner import MAX_CONCURRENT_RUNS
from backend.run_store import store

router = APIRouter(prefix="/api", tags=["System"])


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.1.0"


class ConfigResponse(BaseModel):
    ieee_formats: list[str]
    max_images: int
    accepted_image_types: list[str]
    max_concurrent_runs: int
    run_counts: dict[str, int]
    auth_required: bool
    auth_disabled: bool
    token_url: str


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="2.1.0")


@router.get("/config", response_model=ConfigResponse, summary="Frontend configuration")
def config(_user: UserPublic = Depends(get_current_user)) -> ConfigResponse:
    return ConfigResponse(
        ieee_formats=["journal", "conference"],
        max_images=10,
        accepted_image_types=["image/png", "image/jpeg", "image/webp"],
        max_concurrent_runs=MAX_CONCURRENT_RUNS,
        run_counts=store.counts(),
        auth_required=not auth_disabled(),
        auth_disabled=auth_disabled(),
        token_url="/api/auth/token",
    )
