"""Google OAuth 2.0 / OpenID Connect sign-in and API session tokens."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

bearer_scheme = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"
GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"


class SessionTokenResponse(BaseModel):
    """API session token issued only after Google sign-in (not username/password)."""

    access_token: str = Field(description="Bearer token for AutoPaper API")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Seconds until expiry")


class UserPublic(BaseModel):
    email: str = ""
    name: str = ""
    picture: str = ""
    google_sub: str = ""
    auth_disabled: bool = False

    @property
    def username(self) -> str:
        """Backward-compatible display id (email)."""
        return self.email or self.google_sub or "user"


def auth_disabled() -> bool:
    return os.environ.get("AUTOPAPER_AUTH_DISABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def session_secret() -> str:
    secret = (
        os.environ.get("AUTOPAPER_SESSION_SECRET", "").strip()
        or os.environ.get("AUTOPAPER_JWT_SECRET", "").strip()
    )
    if not secret:
        if auth_disabled():
            return "dev-only-insecure-secret"
        raise RuntimeError(
            "AUTOPAPER_SESSION_SECRET is required when auth is enabled. "
            "Set AUTOPAPER_AUTH_DISABLED=1 for local dev without login."
        )
    return secret


def token_expire_minutes() -> int:
    raw = os.environ.get("AUTOPAPER_SESSION_EXPIRE_MINUTES", "1440").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 1440


def google_client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def google_client_secret() -> str:
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def google_redirect_uri() -> str:
    return os.environ.get(
        "AUTOPAPER_GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/auth/google/callback",
    ).strip()


def frontend_url() -> str:
    return os.environ.get("AUTOPAPER_FRONTEND_URL", "http://localhost:5173").rstrip("/")


def google_oauth_configured() -> bool:
    return bool(google_client_id() and google_client_secret)


def create_session_token(
    *,
    email: str,
    name: str = "",
    picture: str = "",
    google_sub: str = "",
) -> SessionTokenResponse:
    expire = datetime.now(timezone.utc) + timedelta(minutes=token_expire_minutes())
    payload = {
        "sub": email or google_sub,
        "email": email,
        "name": name,
        "picture": picture,
        "google_sub": google_sub,
        "iss": "autopaper-google",
        "exp": expire,
    }
    token = jwt.encode(payload, session_secret(), algorithm=ALGORITHM)
    return SessionTokenResponse(
        access_token=token,
        expires_in=token_expire_minutes() * 60,
    )


def decode_session_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, session_secret(), algorithms=[ALGORITHM])
    if payload.get("iss") != "autopaper-google" and not auth_disabled():
        raise JWTError("Invalid token issuer")
    return payload


def verify_google_id_token(credential: str) -> dict[str, Any]:
    """Verify Google Identity Services `credential` (OpenID Connect id_token)."""
    if not google_client_id():
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_CLIENT_ID is not configured on the server",
        )
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="google-auth package not installed",
        ) from exc

    try:
        return google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            google_client_id(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google credential: {exc}",
        ) from exc


def user_from_google_claims(claims: dict[str, Any]) -> UserPublic:
    email = str(claims.get("email") or "").strip()
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Google account has no email (required)",
        )
    return UserPublic(
        email=email,
        name=str(claims.get("name") or ""),
        picture=str(claims.get("picture") or ""),
        google_sub=str(claims.get("sub") or ""),
    )


async def resolve_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_token: str | None = Query(
        None,
        description="Session token for SSE (EventSource cannot send Authorization)",
    ),
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return access_token


async def get_current_user(
    token: str | None = Depends(resolve_bearer_token),
) -> UserPublic:
    if auth_disabled():
        return UserPublic(
            email="dev@localhost",
            name="Dev",
            auth_disabled=True,
        )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with Google first",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_session_token(token)
        return UserPublic(
            email=str(payload.get("email") or payload.get("sub") or ""),
            name=str(payload.get("name") or ""),
            picture=str(payload.get("picture") or ""),
            google_sub=str(payload.get("google_sub") or ""),
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid — sign in with Google again",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
