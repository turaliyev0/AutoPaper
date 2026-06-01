"""Authentication endpoints (OAuth2 password + JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from backend.auth import (
    TokenResponse,
    UserPublic,
    auth_disabled,
    get_current_user,
    login_for_access_token,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Obtain access token (OAuth2 password flow)",
    description=(
        "Send `username` and `password` as **application/x-www-form-urlencoded** "
        "(OAuth2PasswordRequestForm). Use the returned `access_token` as "
        "`Authorization: Bearer <token>` on all other `/api/*` routes.\n\n"
        "For SSE (`/api/runs/{id}/stream`), pass `?access_token=<token>` because "
        "browser EventSource cannot set Authorization headers."
    ),
)
async def token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    return await login_for_access_token(form_data)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Current user",
)
def me(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return user


@router.get(
    "/status",
    summary="Auth configuration",
)
def auth_status() -> dict:
    return {
        "auth_disabled": auth_disabled(),
        "token_url": "/api/auth/token",
        "scheme": "OAuth2PasswordBearer",
    }
