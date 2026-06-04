"""AutoPaper — backend service (REST + SSE + Google OAuth)."""

from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

from backend.runs.provider_log import normalize_provider_env

normalize_provider_env()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.api import auth_router, runs_router, system_router
from backend.auth import auth_disabled, session_secret

_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"


def _session_middleware_secret() -> str:
    try:
        return session_secret()
    except RuntimeError:
        return os.environ.get("AUTOPAPER_SESSION_SECRET", "dev-session-secret-change-me")


app = FastAPI(
    title="AutoPaper API",
    version="2.2.0",
    description=(
        "IEEE manuscript pipeline with **Google sign-in**.\n\n"
        "**Browser:** open `GET /api/auth/google/login` → Google → callback → "
        "frontend receives `access_token`.\n\n"
        "**SPA:** Google Identity Services → `POST /api/auth/google/verify` "
        "with `{ \"credential\": \"<id_token>\" }`.\n\n"
        "Then: `Authorization: Bearer <access_token>` on all `/api/*` routes. "
        "SSE: `?access_token=<token>` on `/api/runs/{id}/stream`.\n\n"
        "Local dev without Google: `AUTOPAPER_AUTH_DISABLED=1`."
    ),
    contact={"name": "AutoPaper"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=_session_middleware_secret())

app.include_router(auth_router)
app.include_router(system_router)
app.include_router(runs_router)


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    if not auth_disabled():
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "HTTPBearer"
        ] = {
            "type": "http",
            "scheme": "bearer",
            "description": "Session token from Google sign-in (/api/auth/google/*)",
        }
        public_prefixes = (
            "/api/health",
            "/api/auth/google",
            "/api/auth/status",
        )
        for path, methods in schema.get("paths", {}).items():
            if any(path.startswith(p) for p in public_prefixes):
                continue
            for op in methods.values():
                if isinstance(op, dict) and path.startswith("/api/"):
                    op.setdefault("security", [{"HTTPBearer": []}])
    app.openapi_schema = schema
    return app.openapi_schema


if not auth_disabled():
    app.openapi = _custom_openapi  # type: ignore[method-assign]


if _FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def serve_spa(full_path: str = "") -> HTMLResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404)
        index = _FRONTEND_DIST / "index.html"
        if not index.is_file():
            return HTMLResponse("<h1>Frontend not built. Run: npm run build</h1>", 503)
        return HTMLResponse(index.read_text(encoding="utf-8"))
