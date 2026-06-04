"""Verify Google Identity Services id_tokens."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from .config import google_client_id
from .models import UserPublic


def verify_google_id_token(credential: str) -> dict[str, Any]:
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
