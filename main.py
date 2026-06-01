"""AutoPaper — backend service (REST + SSE + OAuth2 JWT)."""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.api.auth_routes import router as auth_router
from backend.api.runs_routes import router as runs_router
from backend.api.system_routes import router as system_router
from backend.auth import auth_disabled

_PROJECT_ROOT = Path(__file__).resolve().parent
_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"

app = FastAPI(
    title="AutoPaper API",
    version="2.1.0",
    description=(
        "IEEE manuscript pipeline with **OAuth2** (JWT bearer).\n\n"
        "1. `POST /api/auth/token` with username/password → `access_token`\n"
        "2. Send `Authorization: Bearer <token>` on protected routes\n"
        "3. SSE: `GET /api/runs/{id}/stream?access_token=<token>`\n\n"
        "Set `AUTOPAPER_AUTH_DISABLED=1` for local dev without login."
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
            "OAuth2PasswordBearer"
        ] = {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": "/api/auth/token",
                    "scopes": {},
                }
            },
        }
        for path, methods in schema.get("paths", {}).items():
            if path.startswith("/api/auth/token") or path == "/api/health":
                continue
            for op in methods.values():
                if isinstance(op, dict) and path.startswith("/api/"):
                    op.setdefault("security", [{"OAuth2PasswordBearer": []}])
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
