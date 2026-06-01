"""Google OAuth sign-in and API session tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.auth import (
    SessionTokenResponse,
    UserPublic,
    auth_disabled,
    create_session_token,
    frontend_url,
    get_current_user,
    google_client_id,
    google_oauth_configured,
    user_from_google_claims,
    verify_google_id_token,
)
from backend.google_oauth import oauth, redirect_uri

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class GoogleCredentialBody(BaseModel):
    """ID token from Google Identity Services (One Tap / Sign-In button)."""

    credential: str = Field(description="Google OIDC id_token JWT")


@router.get(
    "/google/login",
    summary="Start Google sign-in (browser redirect)",
    description=(
        "Redirects the browser to Google. After consent, Google calls "
        "`/api/auth/google/callback`, then the user is sent to the frontend "
        "with `?access_token=...`."
    ),
)
async def google_login(request: Request):
    if auth_disabled():
        tok = create_session_token(
            email="dev@localhost",
            name="Dev",
            google_sub="dev",
        )
        return RedirectResponse(
            f"{frontend_url()}/auth/callback?access_token={tok.access_token}"
        )
    if not google_oauth_configured():
        raise HTTPException(
            503,
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env "
            "(see .env.example).",
        )
    return await oauth.google.authorize_redirect(request, redirect_uri())


@router.get(
    "/google/callback",
    summary="Google OAuth callback (do not call manually)",
    include_in_schema=True,
)
async def google_callback(request: Request):
    if auth_disabled():
        return RedirectResponse(f"{frontend_url()}/")
    if not google_oauth_configured():
        raise HTTPException(503, "Google OAuth not configured")

    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.parse_id_token(request, token)

    user = user_from_google_claims(userinfo)
    session = create_session_token(
        email=user.email,
        name=user.name,
        picture=user.picture,
        google_sub=user.google_sub,
    )
    return RedirectResponse(
        f"{frontend_url()}/auth/callback"
        f"?access_token={session.access_token}"
        f"&token_type={session.token_type}"
        f"&expires_in={session.expires_in}"
    )


@router.post(
    "/google/verify",
    response_model=SessionTokenResponse,
    summary="Exchange Google ID token for API session (SPA)",
    description=(
        "Use when the frontend obtains a `credential` from "
        "[Google Identity Services](https://developers.google.com/identity/gsi/web). "
        "Returns an AutoPaper API `access_token` for `Authorization: Bearer`."
    ),
)
def google_verify(body: GoogleCredentialBody) -> SessionTokenResponse:
    if auth_disabled():
        return create_session_token(
            email="dev@localhost",
            name="Dev",
            google_sub="dev",
        )
    claims = verify_google_id_token(body.credential)
    user = user_from_google_claims(claims)
    return create_session_token(
        email=user.email,
        name=user.name,
        picture=user.picture,
        google_sub=user.google_sub,
    )


@router.get("/me", response_model=UserPublic, summary="Current signed-in user")
def me(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return user


@router.get("/status", summary="Auth configuration for frontend")
def auth_status() -> dict:
    return {
        "auth_disabled": auth_disabled(),
        "provider": "google",
        "google_configured": google_oauth_configured(),
        "google_client_id": google_client_id() if google_oauth_configured() else "",
        "login_url": "/api/auth/google/login",
        "verify_url": "/api/auth/google/verify",
        "frontend_callback": f"{frontend_url()}/auth/callback",
    }
